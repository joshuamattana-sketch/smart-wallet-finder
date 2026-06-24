"use client";

import { useEffect, useRef, useState } from "react";

// ── LM75B — Spiral intro gate ────────────────────────────────────────────────
// A fullscreen branded spiral galaxy shown once per session before the landing.
// "Enter" fades in, the cursor tilts the disk, and a click fades the gate out to
// reveal the page underneath. Client-only (the landing is fully server-rendered
// underneath, so SEO and no-JS visitors get the real page). Respects
// prefers-reduced-motion (static frame, Enter shown immediately) and never
// replays within the same browser session.

const ARMS = 3;
const COUNT = 1700;
const WINDING = 5.0;
const SEEN_KEY = "lumora-intro-seen";

function colorFor(r: number, accent: boolean): [number, number, number] {
  if (accent) return [192, 132, 252]; // neon violet pop (#c084fc)
  if (r < 0.16) return [234, 251, 255]; // near-white core
  if (r < 0.45) return [34, 211, 238]; // cyan (#22d3ee)
  if (r < 0.75) return [139, 92, 246]; // violet (#8b5cf6)
  return [70, 50, 120]; // deep violet, faint
}

type Phase = "hidden" | "in" | "exiting";

export function SpiralIntro() {
  const [phase, setPhase] = useState<Phase>("hidden");
  const [showEnter, setShowEnter] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Client-only: show unless already seen this session.
  useEffect(() => {
    let seen = false;
    try {
      seen = !!sessionStorage.getItem(SEEN_KEY);
    } catch {
      seen = false;
    }
    if (!seen) setPhase("in");
  }, []);

  // Reveal the Enter affordance + lock scroll while the gate is up.
  useEffect(() => {
    if (phase !== "in") return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const t = window.setTimeout(() => setShowEnter(true), reduced ? 0 : 1500);
    return () => {
      window.clearTimeout(t);
      document.body.style.overflow = prevOverflow;
    };
  }, [phase]);

  // Spiral animation (runs while the gate is visible).
  useEffect(() => {
    if (phase === "hidden") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let w = 0;
    let h = 0;
    let mx = 0;
    let my = 0;
    let tx = 0;
    let ty = 0;
    let rot = 0;
    let raf = 0;

    type P = { arm: number; r: number; j: number; sp: number; tw: number; acc: boolean; drift: number };
    const parts: P[] = [];
    for (let i = 0; i < COUNT; i++) {
      parts.push({
        arm: i % ARMS,
        r: Math.pow(Math.random(), 0.7),
        j: (Math.random() - 0.5) * 0.5,
        sp: 0.6 + Math.random() * 0.8,
        tw: Math.random() * 6.28,
        acc: Math.random() < 0.06,
        drift: 0.5 + Math.random(),
      });
    }

    function fit(): boolean {
      const cw = window.innerWidth;
      const ch = window.innerHeight;
      if (!cw || !ch) return false;
      if (cw !== w || ch !== h) {
        w = cw;
        h = ch;
        canvas!.width = Math.round(w * dpr);
        canvas!.height = Math.round(h * dpr);
        ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      return true;
    }

    function draw(advance: boolean) {
      if (!fit()) return;
      if (advance) {
        rot += 0.0016;
        mx += (tx - mx) * 0.05;
        my += (ty - my) * 0.05;
      }
      ctx!.clearRect(0, 0, w, h);
      const cx = w / 2 + mx * 36;
      const cy = h / 2 + my * 24;
      const maxR = Math.min(w, h) * 0.56;
      const tilt = 0.5 - my * 0.12;

      const cg = ctx!.createRadialGradient(cx, cy, 0, cx, cy, 90);
      cg.addColorStop(0, "rgba(200,240,255,0.45)");
      cg.addColorStop(0.4, "rgba(139,92,246,0.16)");
      cg.addColorStop(1, "rgba(139,92,246,0)");
      ctx!.fillStyle = cg;
      ctx!.beginPath();
      ctx!.arc(cx, cy, 90, 0, 6.2832);
      ctx!.fill();

      for (let i = 0; i < COUNT; i++) {
        const p = parts[i];
        if (advance) {
          p.r += 0.00045 * p.drift;
          if (p.r > 1.05) p.r = 0.02 + Math.random() * 0.05;
        }
        const ang = p.arm * (6.2832 / ARMS) + p.r * WINDING + rot * p.sp + p.j;
        const R = p.r * maxR;
        const x = cx + R * Math.cos(ang) + mx * R * 0.04;
        const y = cy + R * Math.sin(ang) * tilt;
        const c = colorFor(p.r, p.acc);
        const tw = 0.6 + 0.4 * Math.sin(p.tw + rot * 60 * p.sp);
        let a = (1 - p.r * 0.7) * tw;
        if (a < 0) a = 0;
        const sz = (1 - p.r) * 2.2 + 0.5;
        ctx!.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${a.toFixed(3)})`;
        ctx!.beginPath();
        ctx!.arc(x, y, sz, 0, 6.2832);
        ctx!.fill();
      }
    }

    function loop() {
      draw(true);
      raf = requestAnimationFrame(loop);
    }

    const onMove = (e: MouseEvent) => {
      tx = e.clientX / window.innerWidth - 0.5;
      ty = e.clientY / window.innerHeight - 0.5;
      if (reduced) draw(false);
    };
    window.addEventListener("mousemove", onMove);
    const onResize = () => draw(false);
    window.addEventListener("resize", onResize);

    const kick = window.setTimeout(() => draw(false), 60);
    if (reduced) {
      requestAnimationFrame(() => draw(false));
    } else {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.clearTimeout(kick);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("resize", onResize);
    };
  }, [phase]);

  function enter() {
    try {
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* ignore */
    }
    document.body.style.overflow = "";
    setPhase("exiting");
    window.setTimeout(() => setPhase("hidden"), 760);
  }

  if (phase === "hidden") return null;

  return (
    <div
      role="dialog"
      aria-label="Lumora intro"
      className="fixed inset-0 z-[120] bg-black transition-opacity duration-700 ease-out"
      style={{
        opacity: phase === "exiting" ? 0 : 1,
        pointerEvents: phase === "exiting" ? "none" : "auto",
      }}
    >
      <canvas ref={canvasRef} aria-hidden className="absolute inset-0 h-full w-full" />

      <div className="absolute left-6 top-5 flex items-center gap-2.5">
        <span className="h-[9px] w-[9px] rounded-[3px] bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.6)]" />
        <span className="text-sm font-medium tracking-wide text-white/85">Lumora</span>
      </div>

      <button
        type="button"
        onClick={enter}
        autoFocus
        aria-label="Enter Lumora"
        className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-2xl font-extralight uppercase tracking-[0.3em] text-white transition-all duration-700 ease-out [text-shadow:0_0_18px_rgba(0,0,0,0.55)] hover:tracking-[0.42em] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-300/60 ${
          showEnter ? "opacity-100" : "translate-y-2 -translate-x-1/2 opacity-0"
        }`}
      >
        Enter
      </button>

      <p
        className={`num absolute bottom-7 left-1/2 -translate-x-1/2 text-[10px] uppercase tracking-[0.3em] text-white/35 transition-opacity duration-700 ${
          showEnter ? "opacity-100" : "opacity-0"
        }`}
      >
        Liquidity intelligence terminal
      </p>
    </div>
  );
}
