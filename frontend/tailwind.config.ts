import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Ink base — a cool desaturated blue-slate, not tinted-near-black.
        ink: {
          900: "#0d1119", // app background
          800: "#141926", // raised surface
          700: "#1b2130", // panel
          600: "#252c3d", // hairline border
          500: "#333c52", // stronger border / divider
        },
        // Text
        fg: {
          DEFAULT: "#e6e9f0",
          muted: "#96a0b5",
          faint: "#5f6a82",
        },
        // Signal colors — each maps to real data states, so color = information.
        signal: {
          live: "#3fd0b8",  // healthy / online / clean
          warn: "#e6a33c",  // findings / warnings
          alert: "#e5574c", // errors / failures
          info: "#5b9dff",  // neutral accent / links
        },
      },
      fontFamily: {
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        panel: "10px",
      },
      keyframes: {
        pulse: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.85)" },
        },
      },
      animation: {
        "status-pulse": "pulse 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;