import { ImageResponse } from "next/og";
import { SITE_NAME } from "@/lib/site";

// LM81B — generated social card. Uses NO remote font fetch (the prior next/og
// attempt crashed on a flaky Google-font request); the built-in font keeps it
// reliable on edge. CSS is kept to what Satori (the @vercel/og renderer)
// actually supports: solid backgroundColor + a single gradient via
// backgroundImage, gradients written angle-first with explicit stops. (An
// earlier graph-paper grid via a stop-less linear-gradient 500'd at render —
// Satori can't parse it.)
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
          backgroundColor: "#0a0b14",
          backgroundImage:
            "radial-gradient(circle at 18% 0%, #17142f 0%, #0a0b14 55%, #06060c 100%)",
          color: "#e8e8f0",
          fontFamily: "sans-serif",
        }}
      >
        {/* Top: brand row */}
        <div style={{ display: "flex", alignItems: "center" }}>
          <div
            style={{
              display: "flex",
              width: 46,
              height: 46,
              borderRadius: 12,
              marginRight: 18,
              backgroundImage: "linear-gradient(135deg, #8b5cf6 0%, #22d3ee 100%)",
              boxShadow: "0 0 40px -6px rgba(139,92,246,0.8)",
            }}
          />
          <div style={{ fontSize: 30, letterSpacing: 8, fontWeight: 700, color: "#ffffff" }}>
            {SITE_NAME.toUpperCase()}
          </div>
          <div style={{ fontSize: 18, letterSpacing: 6, color: "#6b7299", marginLeft: 16 }}>
            TERMINAL
          </div>
        </div>

        {/* Middle: the promise */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              fontSize: 76,
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: -1.5,
              color: "#ffffff",
              maxWidth: 1000,
            }}
          >
            See the liquidity behind the price.
          </div>
          <div style={{ fontSize: 30, color: "#9aa0c2", maxWidth: 900, marginTop: 20 }}>
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
                marginRight: 12,
                backgroundColor: "#22d3ee",
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
