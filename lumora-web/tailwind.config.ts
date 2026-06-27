import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        lumora: {
          bg: "#0a0812",
          surface: "#110d1f",
          card: "#16102a",
          border: "#2a1f4a",
          purple: "#8b5cf6",
          "purple-bright": "#a78bfa",
          cyan: "#22d3ee",
          "cyan-dim": "#0891b2",
          neon: "#c084fc",
          green: "#22c55e",
          red: "#ef4444",
          muted: "#6b7280",
          text: "#e2e8f0",
          "text-dim": "#94a3b8",
        },
        lm: {
          bg: "#0c0c0e",
          surface: "#141416",
          "surface-muted": "#111113",
          border: "#1e1e22",
          text: "#e0e0e4",
          "text-dim": "#a1a1a6",
          muted: "#8a8a92",
          purple: "#8b5cf6",
          cyan: "#22d3ee",
          live: "#22c55e",
          error: "#ef4444",
          warning: "#f59e0b",
          bid: "#22c55e",
          ask: "#ef4444",
        },
        // Isolated "clean fintech" brand for the Gold Bot signal product. Light,
        // serious, Stripe-like — deliberately NOT Lumora's gold/violet. Used ONLY
        // by components under app/bot + components/fintech. Never mix with lm-*.
        fintech: {
          bg: "#FFFFFF",
          ink: "#0F172A",
          "ink-soft": "#475569",
          muted: "#64748B",
          faint: "#94A3B8",
          mist: "#F1F5F9",
          line: "#E2E8F0",
          "line-soft": "#E6E8EE",
          indigo: "#4F46E5",
          "indigo-ink": "#3730A3",
          "indigo-soft": "#EEF0FE",
          "indigo-line": "#DDE0FB",
          pos: "#16A34A",
          neg: "#DC2626",
        },
      },
      backgroundImage: {
        "lumora-gradient": "linear-gradient(135deg, #0a0812 0%, #110d1f 50%, #0d0a1a 100%)",
        "card-gradient": "linear-gradient(135deg, rgba(139,92,246,0.08) 0%, rgba(34,211,238,0.04) 100%)",
        "hero-glow": "radial-gradient(ellipse at 50% 0%, rgba(139,92,246,0.3) 0%, transparent 70%)",
        "purple-glow": "radial-gradient(ellipse at 50% 50%, rgba(139,92,246,0.15) 0%, transparent 70%)",
      },
      fontFamily: {
        mono: ["var(--font-jetbrains-mono)", "'JetBrains Mono'", "Menlo", "Monaco", "Consolas", "monospace"],
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glass: "0 4px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05)",
        "neon-purple": "0 0 20px rgba(139,92,246,0.3)",
        "neon-cyan": "0 0 20px rgba(34,211,238,0.3)",
        card: "0 2px 16px rgba(0,0,0,0.5)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 2s linear infinite",
        "fade-in": "fadeIn 0.4s ease-out",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
