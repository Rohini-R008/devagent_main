// Turn a unix-seconds timestamp into a compact relative string.
export function relativeTime(unixSeconds: number): string {
  const now = Date.now() / 1000;
  const diff = Math.max(0, now - unixSeconds);

  if (diff < 60) return "just now";
  const mins = Math.floor(diff / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(unixSeconds * 1000).toLocaleDateString();
}

// Absolute, human-readable timestamp (used in tooltips / detail rows).
export function absoluteTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString();
}

// Short git SHA.
export function shortSha(sha: string | null): string {
  return sha ? sha.slice(0, 7) : "—";
}