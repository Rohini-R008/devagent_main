"""
Unit tests for app.debug.patterns — the static AST-based checks for
common PyTorch GPU/CUDA memory antipatterns.

Run with:  pytest tests/test_patterns.py -v
"""
import textwrap

import pytest

from app.debug import patterns


def _rules(repo_path) -> set[str]:
    return {f["rule"] for f in patterns.scan_repo(str(repo_path))}


def _write(tmp_path, filename: str, source: str):
    (tmp_path / filename).write_text(textwrap.dedent(source), encoding="utf-8")


# --- missing-zero-grad ---------------------------------------------------

def test_flags_missing_zero_grad(tmp_path):
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer):
            for x, y in loader:
                loss = model(x, y)
                loss.backward()
                optimizer.step()
    """)
    assert "missing-zero-grad" in _rules(tmp_path)


def test_does_not_flag_zero_grad_when_present(tmp_path):
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer):
            for x, y in loader:
                optimizer.zero_grad()
                loss = model(x, y)
                loss.backward()
                optimizer.step()
    """)
    assert "missing-zero-grad" not in _rules(tmp_path)


# --- eval-without-no-grad --------------------------------------------------

def test_flags_eval_without_no_grad(tmp_path):
    _write(tmp_path, "eval.py", """
        def evaluate(model, loader):
            model.eval()
            total = 0
            for x, y in loader:
                total += model(x, y)
            return total
    """)
    assert "eval-without-no-grad" in _rules(tmp_path)


def test_does_not_flag_eval_with_no_grad(tmp_path):
    _write(tmp_path, "eval.py", """
        import torch

        def evaluate(model, loader):
            model.eval()
            total = 0
            with torch.no_grad():
                for x, y in loader:
                    total += model(x, y)
            return total
    """)
    assert "eval-without-no-grad" not in _rules(tmp_path)


# --- tensor-accumulation-without-detach -------------------------------------

def test_flags_tensor_accumulation_without_detach(tmp_path):
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer):
            losses = []
            for x, y in loader:
                optimizer.zero_grad()
                loss = model(x, y)
                loss.backward()
                optimizer.step()
                losses.append(loss)
            return losses
    """)
    assert "tensor-accumulation-without-detach" in _rules(tmp_path)


# --- device-transfer-in-loop -------------------------------------------------

def test_does_not_flag_direct_batch_unpacking(tmp_path):
    """`for x, y in loader: x = x.cuda()` is the normal, correct pattern."""
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer):
            for x, y in loader:
                optimizer.zero_grad()
                x = x.cuda()
                y = y.cuda()
                loss = model(x, y)
                loss.backward()
                optimizer.step()
    """)
    assert "device-transfer-in-loop" not in _rules(tmp_path)


def test_does_not_flag_indirect_batch_unpacking(tmp_path):
    """`for batch in loader: x, y = batch; x = x.cuda()` is also normal."""
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer):
            for batch in loader:
                x, y = batch
                x = x.cuda()
                y = y.cuda()
                optimizer.zero_grad()
                loss = model(x, y)
                loss.backward()
                optimizer.step()
    """)
    assert "device-transfer-in-loop" not in _rules(tmp_path)


def test_flags_model_moved_inside_loop(tmp_path):
    """Moving something other than the batch (e.g. the model) every iteration is a real bug."""
    _write(tmp_path, "train.py", """
        def train_epoch(model, loader, optimizer, device):
            for x, y in loader:
                model = model.to(device)
                optimizer.zero_grad()
                loss = model(x, y)
                loss.backward()
                optimizer.step()
    """)
    assert "device-transfer-in-loop" in _rules(tmp_path)


# --- clean code sanity check -------------------------------------------------

def test_clean_training_code_has_no_findings(tmp_path):
    _write(tmp_path, "train.py", """
        import torch

        def train_epoch(model, loader, optimizer, device):
            losses = []
            for x, y in loader:
                x, y = x.to(device), y.to(device)
                optimizer.zero_grad()
                pred = model(x)
                loss = torch.nn.functional.mse_loss(pred, y)
                loss.backward()
                optimizer.step()
                losses.append(loss.detach())
            return losses

        def evaluate(model, loader, device):
            model.eval()
            total = 0
            with torch.no_grad():
                for x, y in loader:
                    x, y = x.to(device), y.to(device)
                    pred = model(x)
                    total += torch.nn.functional.mse_loss(pred, y).item()
            return total
    """)
    assert patterns.scan_repo(str(tmp_path)) == []


def test_scan_repo_ignores_venv_and_pycache_dirs(tmp_path):
    (tmp_path / ".venv").mkdir()
    _write(tmp_path / ".venv", "should_be_ignored.py", """
        def f():
            for x, y in loader:
                loss.backward()
    """)
    assert patterns.scan_repo(str(tmp_path)) == []


def test_scan_repo_skips_files_with_syntax_errors(tmp_path):
    _write(tmp_path, "broken.py", "def f(:\n    pass")
    # Should not raise — just skip the unparseable file.
    assert patterns.scan_repo(str(tmp_path)) == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))