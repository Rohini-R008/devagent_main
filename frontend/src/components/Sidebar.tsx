"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HealthPulse } from "./HealthPulse";

const nav = [
  { href: "/", label: "Reviews", desc: "PR review history" },
  { href: "/debug", label: "Debug", desc: "GPU-memory console" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-ink-600 bg-ink-800">
      <div className="border-b border-ink-600 px-5 py-5">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-lg font-semibold tracking-tight text-fg">
            devagent
          </span>
        </div>
        <p className="mt-1 text-xs text-fg-faint">
          Autonomous review &amp; debug
        </p>
        <div className="mt-4">
          <HealthPulse />
        </div>
      </div>

      <nav className="flex flex-col gap-1 p-3">
        {nav.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group rounded-panel border px-3 py-2.5 transition-colors ${
                active
                  ? "border-ink-500 bg-ink-700"
                  : "border-transparent hover:border-ink-600 hover:bg-ink-700/50"
              }`}
            >
              <span
                className={`block text-sm ${
                  active ? "text-fg" : "text-fg-muted group-hover:text-fg"
                }`}
              >
                {item.label}
              </span>
              <span className="block text-xs text-fg-faint">{item.desc}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-ink-600 px-5 py-4">
        <p className="font-mono text-[11px] leading-relaxed text-fg-faint">
          v0.1.0
        </p>
      </div>
    </aside>
  );
}