"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, MessageCircle } from "lucide-react";
import { DISCORD_URL } from "@/lib/site";

// ── LM75A — Spiral hero ──────────────────────────────────────────────────────
// A branded spiral galaxy: thousands of liquidity particles (cyan/teal) wind
// into a glowing core, with sparse amber accents reading as whales. The disk
// tilts toward the cursor. Calm, looping, no GSAP — plain canvas 2D.
//
// Self-sizing each frame (robust to 0-width at mount). Respects
// prefers-reduced-motion (single static frame) and pauses off-screen.

const ARMS = 3;
const COUNT = 1300;
const WINDING = 5.0;

function colorFor(r: number, accent: boolean): [number, number, number] {
  if (accent) return [245, 158, 11];
  if (r < 0.16) return [225, 253, 250];
  if (r < 0.5) return [45, 212, 191];
  if (r < 0.78) return [31, 111, 134];
  return [20, 64, 106];
}

export function SpiralHero() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
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
    let visible = true;

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
      const cw = host!.clientWidth;
      const ch = host!.clientHeight;
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
      const cx = w * 0.66 + mx * 30;
      const cy = h * 0.46 + my * 20;
      const maxR = Math.min(w, h) * 0.62;
      const tilt = 0.46 - my * 0.12;

      const cg = ctx!.createRadialGradient(cx, cy, 0, cx, cy, 72);
      cg.addColorStop(0, "rgba(190,250,245,0.5)");
      cg.addColorStop(0.4, "rgba(45,212,191,0.16)");
      cg.addColorStop(1, "rgba(45,212,191,0)");
      ctx!.fillStyle = cg;
      ctx!.beginPath();
      ctx!.arc(cx, cy, 72, 0, 6.2832);
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
        const sz = (1 - p.r) * 2.0 + 0.5;
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
      const r = host!.getBoundingClientRect();
      tx = (e.clientX - r.left) / r.width - 0.5;
      ty = (e.clientY - r.top) / r.height - 0.5;
      if (reduced) draw(false);
    };
    const onLeave = () => {
      tx = 0;
      ty = 0;
    };
    host.addEventListener("mousemove", onMove);
    host.addEventListener("mouseleave", onLeave);

    const ro = new ResizeObserver(() => draw(false));
    ro.observe(host);

    // Guaranteed first paint independent of rAF (covers throttled/hidden tabs
    // and the initial 0-width layout race).
    const kick = setTimeout(() => draw(false), 60);

    let io: IntersectionObserver | null = null;
    if (reduced) {
      requestAnimationFrame(() => draw(false));
    } else {
      raf = requestAnimationFrame(loop);
      io = new IntersectionObserver(
        ([entry]) => {
          visible = entry.isIntersecting;
          if (visible && !raf) raf = requestAnimationFrame(loop);
          if (!visible && raf) {
            cancelAnimationFrame(raf);
            raf = 0;
          }
        },
        { threshold: 0 },
      );
      io.observe(host);
    }

    return () => {
      if (raf) cancelAnimationFrame(raf);
      clearTimeout(kick);
      host.removeEventListener("mousemove", onMove);
      host.removeEventListener("mouseleave", onLeave);
      ro.disconnect();
      if (io) io.disconnect();
    };
  }, []);

  return (
    <section
      ref={hostRef}
      aria-labelledby="hero-heading"
      className="relative h-[clamp(520px,82vh,760px)] w-full overflow-hidden"
    >
      <canvas ref={canvasRef} aria-hidden className="absolute inset-0 h-full w-full" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(58% 58% at 66% 46%, rgba(45,212,191,0.10), transparent 60%)",
        }}
      />

      <div className="pointer-events-none absolute inset-x-0 top-0 px-4 pt-16 sm:pt-20">
        <div className="mx-auto max-w-6xl">
          <p className="num text-[10px] uppercase tracking-[0.28em] text-lm-muted">
            Liquidity intelligence terminal
          </p>
          <h1
            id="hero-heading"
            className="mt-4 max-w-xl font-semibold leading-[1.03] tracking-[-0.02em] text-lm-text text-[clamp(2rem,7vw,3.25rem)]"
          >
            See the pressure
            <br />
            behind the <span className="text-cyan-300">price</span>.
          </h1>
          <p className="mt-4 max-w-sm text-[14px] leading-relaxed text-lm-text-dim">
            Thousands of signals — orderbook depth, whale flow and funding —
            spiralling into one read.
          </p>
          <div className="pointer-events-auto mt-7 flex flex-col gap-2.5 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 text-[13px] font-semibold text-zinc-950 shadow-[0_0_28px_rgba(34,211,238,0.25)] transition-all hover:bg-cyan-300 hover:shadow-[0_0_36px_rgba(34,211,238,0.4)]"
            >
              Open the demo terminal <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <a
              href={DISCORD_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-lm-border px-5 text-[13px] font-medium text-lm-text-dim transition-colors hover:border-zinc-600 hover:text-lm-text"
            >
              <MessageCircle className="h-3.5 w-3.5 text-lm-cyan" />
              Join the Discord
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
