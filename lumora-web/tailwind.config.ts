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
      },
      backgroundImage: {
        "lumora-gradient": "linear-gradient(135deg, #0a0812 0%, #110d1f 50%, #0d0a1a 100%)",
        "card-gradient": "linear-gradient(135deg, rgba(139,92,246,0.08) 0%, rgba(34,211,238,0.04) 100%)",
        "hero-glow": "radial-gradient(ellipse at 50% 0%, rgba(139,92,246,0.3) 0%, transparent 70%)",
        "purple-glow": "radial-gradient(ellipse at 50% 50%, rgba(139,92,246,0.15) 0%, transparent 70%)",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "Menlo", "Monaco", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
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
