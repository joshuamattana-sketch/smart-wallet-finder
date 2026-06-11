"use client";

// ── TopNav (LM69C final nav refinement) ──────────────────────────────────────
// A dark terminal command bar, not a SaaS tab strip. Visual language matches
// the IntelligenceDock: deep navy glass, recessed control rails, violet =
// selected/brand, cyan reserved for live energy. All styling is local
// Tailwind — no global nav classes.
//
// Anatomy:
//   brand block  — violet→cyan gradient mark tile + LUMORA + TERMINAL suffix
//   link rail    — one recessed glass channel; links ride inside it.
//                  Active: gradient violet surface + luminous violet→cyan
//                  bottom edge. Hover: soft halo, 1px lift, press feedback.
//   status rail  — UTC clock + LIVE pulse fused in a matching channel.
// All motion ≤200ms and motion-reduce gated.

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { Activity, LayoutDashboard, Monitor, Layers, Bell, BookOpen } from "lucide-react";

const navLinks = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/terminal", label: "Terminal", icon: Monitor },
  { href: "/liquidity-map", label: "Liquidity Map", icon: Layers },
  { href: "/whale-alerts", label: "Whale Alerts", icon: Bell },
  { href: "/paper-trading", label: "Paper Trading", icon: BookOpen },
];

export function TopNav() {
  const pathname = usePathname();

  // Session clock — quiet terminal detail, client-only to avoid hydration
  // mismatch. Information, not motion, so no reduced-motion gating needed.
  const [utc, setUtc] = useState<string | null>(null);
  useEffect(() => {
    const tick = () => setUtc(new Date().toISOString().slice(11, 19));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-white/[0.06] bg-gradient-to-b from-[#0c0e16]/95 to-[#0a0a10]/90 shadow-[0_12px_32px_-18px_rgba(0,0,0,0.95)] backdrop-blur-xl">
      {/* machined top highlight + brand edge-light along the bottom */}
      <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/[0.05]" />
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-violet-500/25 to-cyan-400/10"
      />

      <div className="mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-12 items-center gap-3 sm:gap-4">
          {/* Brand block — gradient mark tile + wordmark + terminal suffix */}
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-cyan-400/60"
          >
            <span className="relative flex h-[26px] w-[26px] items-center justify-center rounded-md border border-violet-400/30 bg-gradient-to-br from-violet-500/[0.22] to-cyan-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_14px_-6px_rgba(139,92,246,0.6)] transition-all duration-200 group-hover:border-violet-300/50 group-hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_0_16px_-4px_rgba(139,92,246,0.7)]">
              <Activity className="h-3.5 w-3.5 text-violet-200" strokeWidth={2.5} />
            </span>
            <span className="flex items-baseline gap-1.5">
              <span className="lm-brand text-[14px] tracking-[0.05em] text-lm-text transition-colors duration-150 group-hover:text-white">
                LUMORA
              </span>
              <span className="num hidden text-[8.5px] uppercase tracking-[0.26em] text-lm-muted md:inline">
                Terminal
              </span>
            </span>
          </Link>

          {/* Link rail — one recessed glass channel holding the page links */}
          <div className="lm-no-scrollbar flex min-w-0 flex-1 items-center overflow-x-auto">
            <div className="flex items-center gap-0.5 rounded-lg border border-white/[0.05] bg-black/25 p-0.5 shadow-[inset_0_1px_3px_rgba(0,0,0,0.45),inset_0_-1px_0_rgba(255,255,255,0.02)]">
              {navLinks.map(({ href, label, icon: Icon }) => {
                const isActive = pathname === href || pathname.startsWith(href + "/");
                return (
                  <Link
                    key={href}
                    href={href}
                    title={label}
                    className={clsx(
                      "group relative flex shrink-0 items-center gap-1.5 rounded-[7px] px-2 py-1.5 text-[12.5px] font-medium sm:px-2.5",
                      "transition-[background-color,color,transform,box-shadow] duration-150 ease-out",
                      "active:translate-y-0 active:scale-[0.985]",
                      "motion-reduce:transition-none motion-reduce:hover:translate-y-0 motion-reduce:active:scale-100",
                      "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1 focus-visible:outline-cyan-400/60",
                      isActive
                        ? "bg-gradient-to-b from-violet-500/[0.18] to-violet-500/[0.07] text-white shadow-[inset_0_0_0_1px_rgba(139,92,246,0.22),inset_0_1px_0_rgba(255,255,255,0.06)]"
                        : "text-lm-text-dim hover:-translate-y-px hover:bg-white/[0.05] hover:text-lm-text hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]",
                    )}
                  >
                    {/* hover halo — quiet violet bloom behind the link */}
                    {!isActive && (
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-0 rounded-[7px] bg-[radial-gradient(ellipse_at_center,rgba(139,92,246,0.10),transparent_70%)] opacity-0 transition-opacity duration-200 group-hover:opacity-100 motion-reduce:transition-none"
                      />
                    )}
                    <Icon
                      className={clsx(
                        "relative h-3.5 w-3.5 shrink-0 transition-colors duration-150 motion-reduce:transition-none",
                        isActive ? "text-violet-300" : "text-lm-muted group-hover:text-lm-text-dim",
                      )}
                    />
                    <span className="relative hidden lg:inline">{label}</span>
                    {/* luminous active edge — violet→cyan on the pill's lower lip */}
                    {isActive && (
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-x-1.5 bottom-0 h-px rounded-full bg-gradient-to-r from-violet-400/90 via-cyan-300/70 to-transparent shadow-[0_0_8px_rgba(139,92,246,0.55)]"
                      />
                    )}
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Status rail — UTC session clock + live pulse, matching channel */}
          <div className="ml-auto flex shrink-0 items-center">
            <div className="num flex items-center gap-2 rounded-lg border border-white/[0.05] bg-black/25 px-2.5 py-[5px] shadow-[inset_0_1px_3px_rgba(0,0,0,0.45),inset_0_-1px_0_rgba(255,255,255,0.02)]">
              {utc && (
                <>
                  <span className="hidden text-[10.5px] tracking-wide text-lm-text-dim md:inline">
                    {utc} <span className="text-lm-muted">UTC</span>
                  </span>
                  <span aria-hidden className="hidden h-3 w-px bg-white/[0.08] md:block" />
                </>
              )}
              <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-emerald-300/90">
                <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 text-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" />
                <span className="hidden sm:inline">Live</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
