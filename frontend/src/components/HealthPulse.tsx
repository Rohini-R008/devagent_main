"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type State = "checking" | "online" | "offline";

// The signature element: a live readout of whether the agent backend is
// reachable. Polls /health on an interval so the console always reflects
// current reality.
export function HealthPulse() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    let active = true;

    const check = async () => {
      try {
        const res = await api.health();
        if (active) setState(res.status === "ok" ? "online" : "offline");
      } catch {
        if (active) setState("offline");
      }
    };

    check();
    const id = setInterval(check, 15000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const config = {
    checking: { dot: "bg-fg-faint", label: "Connecting", text: "text-fg-faint" },
    online: { dot: "bg-signal-live", label: "Agent online", text: "text-signal-live" },
    offline: { dot: "bg-signal-alert", label: "Agent offline", text: "text-signal-alert" },
  }[state];

  return (
    <div className="flex items-center gap-2.5">
      <span className="relative flex h-2.5 w-2.5">
        {state === "online" && (
          <span className="absolute inline-flex h-full w-full animate-status-pulse rounded-full bg-signal-live" />
        )}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${config.dot}`} />
      </span>
      <span className={`text-sm ${config.text}`}>{config.label}</span>
    </div>
  );
}