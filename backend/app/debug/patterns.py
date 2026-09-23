"""
Lightweight static checks for common PyTorch patterns that lead to GPU/CUDA
memory fragmentation or leaks. These are heuristics (regex/AST-based), meant
to flag likely spots for the LLM to reason about with real code context —
not a full data-flow analysis.
"""
import ast
from pathlib import Path

Finding = dict  # {"file": str, "line": int, "rule": str, "message": str}


def _walk_python_files(repo_path: str):
    for path in Path(repo_path).rglob("*.py"):
        if any(part in {".venv", "venv", "node_modules", "__pycache__", ".git"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        yield path, text


class _MemoryPatternVisitor(ast.NodeVisitor):
    """Walks a single file's AST looking for known GPU-memory antipatterns."""

    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.findings: list[Finding] = []
        self._loop_depth = 0
        self._has_no_grad_ctx = 0
        self._loop_target_names: set[str] = set()
        self._loop_scopes: list[set[str]] = []  # names introduced per enclosing for-loop

    def _add(self, node: ast.AST, rule: str, message: str):
        self.findings.append({
            "file": self.rel_path,
            "line": getattr(node, "lineno", 0),
            "rule": rule,
            "message": message,
        })

    def _target_names(self, target: ast.AST) -> set[str]:
        """Collect variable names bound by a for-loop target, e.g. `for x, y in loader`."""
        names = set()
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                names.add(n.id)
        return names

    # --- loop tracking, to catch per-iteration allocation patterns ---
    def visit_For(self, node: ast.For):
        self._loop_depth += 1
        scope = self._target_names(node.target)
        self._loop_scopes.append(scope)
        self._loop_target_names |= scope
        self.generic_visit(node)
        self._loop_target_names -= self._loop_scopes.pop()
        self._loop_depth -= 1

    def visit_Assign(self, node: ast.Assign):
        # Recognize indirect unpacking of the loop's batch variable, e.g.
        #   for batch in loader:
        #       x, y = batch
        # so `x`/`y` are still treated as normal per-batch variables, not
        # flagged as "moved to device inside a loop" antipatterns.
        if self._loop_scopes and isinstance(node.value, ast.Name) \
                and node.value.id in self._loop_target_names:
            derived = set()
            for t in node.targets:
                derived |= self._target_names(t)
            self._loop_scopes[-1] |= derived
            self._loop_target_names |= derived
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_With(self, node: ast.With):
        is_no_grad = any(
            _is_call_named(item.context_expr, {"no_grad", "inference_mode"})
            for item in node.items
        )
        if is_no_grad:
            self._has_no_grad_ctx += 1
            self.generic_visit(node)
            self._has_no_grad_ctx -= 1
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # `.cuda()` / `.to(device)` called repeatedly inside a loop body.
        # Skip when it's the loop's own batch variable (normal dataloader pattern:
        # `x, y = x.to(device), y.to(device)`) — only flag transfers of something
        # else (e.g. the model, or a tensor built outside the loop).
        if self._loop_depth > 0 and _is_attr_call_named(node, {"cuda", "to"}):
            target = node.func.value
            is_batch_var = isinstance(target, ast.Name) and target.id in self._loop_target_names
            if not is_batch_var:
                self._add(
                    node, "device-transfer-in-loop",
                    "Tensor/model moved to device inside a loop, but it isn't the loop's "
                    "own per-iteration variable — if this value doesn't change between "
                    "iterations, move the .to()/.cuda() call outside the loop."
                )

        # Accumulating a tensor into a Python list without .detach()/.item()
        # e.g. `losses.append(loss)` where loss still carries the graph.
        if _is_attr_call_named(node, {"append"}) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Name) and not self._has_no_grad_ctx:
                self._add(
                    node, "tensor-accumulation-without-detach",
                    f"'{arg.id}' is appended to a list — if this is a loss/metric tensor "
                    "still attached to the autograd graph, call .detach() or .item() first "
                    "to avoid retaining the whole computation graph across iterations."
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Training-loop-shaped function with backward() but no zero_grad() anywhere in it
        source_calls = {n.func.attr for n in ast.walk(node)
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        if "backward" in source_calls and "zero_grad" not in source_calls:
            self._add(
                node, "missing-zero-grad",
                f"Function '{node.name}' calls .backward() but no .zero_grad() call was "
                "found in it — gradients may accumulate unintentionally across steps, "
                "growing memory use."
            )
        # eval-shaped function (has .eval()) without a no_grad/inference_mode context anywhere
        if "eval" in source_calls and self._has_no_grad_ctx == 0:
            has_no_grad_inside = any(
                isinstance(n, ast.With) and any(
                    _is_call_named(item.context_expr, {"no_grad", "inference_mode"})
                    for item in n.items
                )
                for n in ast.walk(node)
            )
            if not has_no_grad_inside:
                self._add(
                    node, "eval-without-no-grad",
                    f"Function '{node.name}' calls .eval() but doesn't appear to wrap "
                    "inference in torch.no_grad()/inference_mode() — this keeps the "
                    "autograd graph alive and wastes GPU memory during evaluation."
                )
        self.generic_visit(node)


def _is_call_named(node: ast.AST, names: set[str]) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr in names
    if isinstance(node, ast.Name):
        return node.id in names
    return False


def _is_attr_call_named(node: ast.Call, names: set[str]) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr in names


def scan_repo(repo_path: str) -> list[Finding]:
    """Run all static checks across every .py file in the repo."""
    findings: list[Finding] = []
    for path, text in _walk_python_files(repo_path):
        rel_path = str(path.relative_to(repo_path))
        try:
            tree = ast.parse(text, filename=rel_path)
        except SyntaxError:
            continue
        visitor = _MemoryPatternVisitor(rel_path)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings