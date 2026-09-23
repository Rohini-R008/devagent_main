"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Review } from "@/lib/types";
import { relativeTime, absoluteTime, shortSha } from "@/lib/format";
import { Badge, Panel, Spinner, EmptyState, ErrorNote } from "./ui";

function SandboxBadge({ code }: { code: number | null }) {
  if (code === null) return <span className="text-fg-faint">—</span>;
  if (code === 0)
    return (
      <Badge tone="live" mono>
        exit 0
      </Badge>
    );
  return (
    <Badge tone="alert" mono>
      exit {code}
    </Badge>
  );
}

function StatReadout({ reviews }: { reviews: Review[] }) {
  const total = reviews.length;
  const comments = reviews.reduce((s, r) => s + (r.comment_count ?? 0), 0);
  const withIssues = reviews.filter(
    (r) => r.error || (r.sandbox_exit_code != null && r.sandbox_exit_code !== 0)
  ).length;

  const stats: { label: string; value: number }[] = [
    { label: "Reviews run", value: total },
    { label: "Comments posted", value: comments },
    { label: "Runs with issues", value: withIssues },
  ];

  return (
    <div className="grid grid-cols-3 gap-3">
      {stats.map((s) => (
        <Panel key={s.label} className="px-4 py-3.5">
          <p className="text-xs text-fg-faint">{s.label}</p>
          <p className="mt-1 font-mono text-2xl text-fg">{s.value}</p>
        </Panel>
      ))}
    </div>
  );
}

export function ReviewsView() {
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      setReviews(await api.listReviews());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reviews.");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl text-fg">Review history</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Every pull request the agent has reviewed, newest first.
          </p>
        </div>
        <button
          onClick={load}
          disabled={refreshing}
          className="rounded-panel border border-ink-600 bg-ink-700 px-3 py-1.5 text-sm text-fg-muted transition-colors hover:border-ink-500 hover:text-fg disabled:opacity-50"
        >
          {refreshing ? <Spinner /> : "Refresh"}
        </button>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {reviews === null && !error && (
        <div className="py-14 text-center">
          <Spinner label="Loading reviews…" />
        </div>
      )}

      {reviews && reviews.length > 0 && (
        <>
          <StatReadout reviews={reviews} />

          <Panel className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-600 text-left text-xs text-fg-faint">
                  <th className="px-4 py-3 font-normal">Repository</th>
                  <th className="px-4 py-3 font-normal">PR</th>
                  <th className="px-4 py-3 font-normal">Summary</th>
                  <th className="px-4 py-3 font-normal">Comments</th>
                  <th className="px-4 py-3 font-normal">Sandbox</th>
                  <th className="px-4 py-3 font-normal">Commit</th>
                  <th className="px-4 py-3 text-right font-normal">When</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-ink-700 last:border-0 align-top hover:bg-ink-700/40"
                  >
                    <td className="px-4 py-3 font-mono text-fg">
                      {r.repo_full_name}
                    </td>
                    <td className="px-4 py-3 font-mono text-signal-info">
                      #{r.pr_number}
                    </td>
                    <td className="max-w-md px-4 py-3 text-fg-muted">
                      {r.error ? (
                        <span className="text-signal-alert">{r.error}</span>
                      ) : (
                        r.summary || <span className="text-fg-faint">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-fg-muted">
                      {r.comment_count ?? 0}
                    </td>
                    <td className="px-4 py-3">
                      <SandboxBadge code={r.sandbox_exit_code} />
                    </td>
                    <td className="px-4 py-3 font-mono text-fg-faint">
                      {shortSha(r.head_sha)}
                    </td>
                    <td
                      className="px-4 py-3 text-right text-fg-faint"
                      title={absoluteTime(r.created_at)}
                    >
                      {relativeTime(r.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}

      {reviews && reviews.length === 0 && !error && (
        <EmptyState
          title="No reviews yet"
          hint="When a pull request is opened on a connected repository, the agent reviews it and the result shows up here."
        />
      )}
    </div>
  );
}