import { ReactNode } from "react";

type Tone = "live" | "warn" | "alert" | "info" | "neutral";

const toneClasses: Record<Tone, string> = {
  live: "text-signal-live border-signal-live/30 bg-signal-live/10",
  warn: "text-signal-warn border-signal-warn/30 bg-signal-warn/10",
  alert: "text-signal-alert border-signal-alert/30 bg-signal-alert/10",
  info: "text-signal-info border-signal-info/30 bg-signal-info/10",
  neutral: "text-fg-muted border-ink-500 bg-ink-700",
};

export function Badge({
  children,
  tone = "neutral",
  mono = false,
}: {
  children: ReactNode;
  tone?: Tone;
  mono?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${
        mono ? "font-mono" : ""
      } ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-panel border border-ink-600 bg-ink-800 ${className}`}
    >
      {children}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-fg-muted">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-500 border-t-signal-info" />
      {label && <span className="text-sm">{label}</span>}
    </span>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 border border-dashed border-ink-500 rounded-panel px-6 py-14 text-center">
      <p className="text-fg">{title}</p>
      {hint && <p className="max-w-sm text-sm text-fg-faint">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-panel border border-signal-alert/40 bg-signal-alert/10 px-4 py-3 text-sm text-signal-alert">
      {children}
    </div>
  );
}