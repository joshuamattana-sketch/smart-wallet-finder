import { ImageResponse } from "next/og";
import { SITE_NAME } from "@/lib/site";

// LM81B — generated social card. Deliberately uses NO remote font fetch (the
// previous next/og attempt crashed on a flaky Google-font request); the
// built-in font keeps it reliable on edge. Dark terminal look: graph-paper
// grid, violet/cyan glow, the wordmark, and the one-line product promise.
export const runtime = "edge";
export const alt = "Lumora — liquidity intelligence terminal for crypto";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background:
            "radial-gradient(120% 120% at 15% 0%, #14132b 0%, #0a0b12 55%, #07070d 100%)",
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          color: "#e8e8f0",
          fontFamily: "sans-serif",
        }}
      >
        {/* Top: brand row */}
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              display: "flex",
              width: 46,
              height: 46,
              borderRadius: 12,
              background: "linear-gradient(150deg, #8b5cf6 0%, #6366f1 60%, #22d3ee 100%)",
              boxShadow: "0 0 40px -6px rgba(139,92,246,0.8)",
            }}
          />
          <div
            style={{
              fontSize: 30,
              letterSpacing: 8,
              fontWeight: 700,
              color: "#ffffff",
            }}
          >
            {SITE_NAME.toUpperCase()}
          </div>
          <div style={{ fontSize: 18, letterSpacing: 6, color: "#6b7299" }}>TERMINAL</div>
        </div>

        {/* Middle: the promise */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              fontSize: 76,
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: -1.5,
              color: "#ffffff",
              maxWidth: 980,
            }}
          >
            See the liquidity behind the price.
          </div>
          <div style={{ fontSize: 30, color: "#9aa0c2", maxWidth: 900, lineHeight: 1.3 }}>
            Orderbook depth, whale flow, funding and sweep-risk zones — distilled into one
            market read.
          </div>
        </div>

        {/* Bottom: url + beta */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 26, color: "#c4b5fd", letterSpacing: 1 }}>lumora-app.app</div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 20,
              letterSpacing: 4,
              color: "#a5f3fc",
            }}
          >
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: 999,
                background: "#22d3ee",
                boxShadow: "0 0 14px 2px rgba(34,211,238,0.7)",
              }}
            />
            PRIVATE BETA
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
