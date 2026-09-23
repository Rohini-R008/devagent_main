"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DebugResult, DebugScan } from "@/lib/types";
import { relativeTime, absoluteTime } from "@/lib/format";
import { Badge, Panel, Spinner, EmptyState, ErrorNote } from "./ui";

type Mode = "scan" | "analyze";

function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded border border-ink-600 bg-ink-900 p-3 font-mono text-xs leading-relaxed text-fg">
      <code>{code}</code>
    </pre>
  );
}

function ResultView({ result }: { result: DebugResult }) {
  return (
    <div className="space-y-4">
      <Panel className="px-4 py-4">
        <p className="text-xs text-fg-faint">Root cause</p>
        <p className="mt-1.5 text-sm leading-relaxed text-fg">
          {result.root_cause_summary}
        </p>
      </Panel>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm text-fg">Diagnosed issues</h3>
          <Badge tone={result.issues.length ? "warn" : "live"} mono>
            {result.issues.length}
          </Badge>
        </div>
        {result.issues.length === 0 ? (
          <p className="text-sm text-fg-faint">
            No concrete issues diagnosed.
          </p>
        ) : (
          <div className="space-y-3">
            {result.issues.map((issue, i) => (
              <Panel key={i} className="px-4 py-4">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-signal-info">
                    {issue.file}:{issue.line}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-fg">
                  {issue.problem}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-fg-muted">
                  <span className="text-fg-faint">Fix — </span>
                  {issue.fix}
                </p>
                {issue.patch && <CodeBlock code={issue.patch} />}
              </Panel>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm text-fg">Static findings</h3>
          <Badge tone={result.static_findings.length ? "warn" : "live"} mono>
            {result.static_findings.length}
          </Badge>
        </div>
        {result.static_findings.length === 0 ? (
          <p className="text-sm text-fg-faint">
            No antipatterns flagged by the heuristic checks.
          </p>
        ) : (
          <Panel className="divide-y divide-ink-700">
            {result.static_findings.map((f, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3">
                <Badge tone="warn" mono>
                  {f.rule}
                </Badge>
                <div className="min-w-0">
                  <p className="font-mono text-xs text-fg-muted">
                    {f.file}:{f.line}
                  </p>
                  <p className="mt-1 text-sm text-fg">{f.message}</p>
                </div>
              </div>
            ))}
          </Panel>
        )}
      </div>
    </div>
  );
}

function History() {
  const [scans, setScans] = useState<DebugScan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setScans(await api.debugHistory());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (scans === null) return <Spinner label="Loading history…" />;
  if (scans.length === 0)
    return (
      <EmptyState
        title="No past runs"
        hint="Scans and traceback analyses you run will be recorded here."
      />
    );

  return (
    <Panel className="divide-y divide-ink-700">
      {scans.map((s) => (
        <div key={s.id} className="px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Badge tone="info" mono>
                {s.mode}
              </Badge>
              <span className="font-mono text-xs text-fg-muted">
                {s.repo_path}
              </span>
            </div>
            <span
              className="shrink-0 text-xs text-fg-faint"
              title={absoluteTime(s.created_at)}
            >
              {relativeTime(s.created_at)}
            </span>
          </div>
          {s.root_cause_summary && (
            <p className="mt-2 text-sm text-fg-muted">{s.root_cause_summary}</p>
          )}
          <div className="mt-2 flex gap-2 text-xs text-fg-faint">
            <span>{s.issue_count ?? 0} issues</span>
            <span>·</span>
            <span>{s.static_finding_count ?? 0} findings</span>
          </div>
        </div>
      ))}
    </Panel>
  );
}

export function DebugConsole() {
  const [mode, setMode] = useState<Mode>("scan");
  const [repoPath, setRepoPath] = useState("");
  const [traceback, setTraceback] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DebugResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyKey, setHistoryKey] = useState(0);

  const canRun =
    repoPath.trim().length > 0 &&
    (mode === "scan" || traceback.trim().length > 0) &&
    !running;

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res =
        mode === "scan"
          ? await api.scanRepo(repoPath.trim())
          : await api.analyzeTraceback(repoPath.trim(), traceback.trim());
      setResult(res);
      setHistoryKey((k) => k + 1); // refresh history after a successful run
    } catch (e) {
      setError(e instanceof Error ? e.message : "The run failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl text-fg">Memory debugger</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Point the agent at a repository to scan for GPU-memory antipatterns,
          or paste a traceback for a targeted diagnosis.
        </p>
      </div>

      <Panel className="space-y-4 p-5">
        <div className="inline-flex rounded-panel border border-ink-600 bg-ink-900 p-1">
          {(["scan", "analyze"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded px-3 py-1.5 text-sm transition-colors ${
                mode === m
                  ? "bg-ink-700 text-fg"
                  : "text-fg-muted hover:text-fg"
              }`}
            >
              {m === "scan" ? "Scan repository" : "Analyze traceback"}
            </button>
          ))}
        </div>

        <div>
          <label className="block text-sm text-fg-muted">
            Repository path
          </label>
          <input
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/absolute/path/to/repo"
            spellCheck={false}
            className="mt-1.5 w-full rounded-panel border border-ink-600 bg-ink-900 px-3 py-2 font-mono text-sm text-fg placeholder:text-fg-faint focus:border-signal-info focus:outline-none"
          />
          <p className="mt-1 text-xs text-fg-faint">
            A path the backend can read on the machine running the API.
          </p>
        </div>

        {mode === "analyze" && (
          <div>
            <label className="block text-sm text-fg-muted">Traceback</label>
            <textarea
              value={traceback}
              onChange={(e) => setTraceback(e.target.value)}
              placeholder="Paste the full error traceback here…"
              rows={8}
              spellCheck={false}
              className="mt-1.5 w-full resize-y rounded-panel border border-ink-600 bg-ink-900 px-3 py-2 font-mono text-xs leading-relaxed text-fg placeholder:text-fg-faint focus:border-signal-info focus:outline-none"
            />
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={run}
            disabled={!canRun}
            className="rounded-panel bg-signal-info px-4 py-2 text-sm font-medium text-ink-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Running…" : mode === "scan" ? "Run scan" : "Analyze"}
          </button>
          {running && <Spinner label="The agent is thinking…" />}
        </div>
      </Panel>

      {error && <ErrorNote>{error}</ErrorNote>}

      {result && <ResultView result={result} />}

      <div>
        <h2 className="mb-3 text-sm text-fg">Past runs</h2>
        <History key={historyKey} />
      </div>
    </div>
  );
}