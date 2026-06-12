"use client";

// ── TopNav (LM69D premium redesign) ──────────────────────────────────────────
// Inspiration: Limelight Nav (sliding top-edge indicator), Glow Menu (per-item
// radial bloom), cinematic trading terminal (Bloomberg, Refinitiv depth).
// Key upgrades over LM69C:
//   • framer-motion layoutId sliding active-pill — snaps across tabs on route
//   • limelight top-edge bar slides with active pill (not static per-item)
//   • stronger brand mark: larger tile, violet pulse, LUMORA glow
//   • active item: brighter text, violet icon, internal luminance cone
//   • status rail: cyan ambient halo behind LIVE dot
//   • nav bar: thicker glass atmosphere, stronger bottom separator sweep

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import { Activity, LayoutDashboard, Monitor, Layers, Bell, BookOpen } from "lucide-react";

const navLinks = [
  { href: "/dashboard",     label: "Dashboard",    icon: LayoutDashboard },
  { href: "/terminal",      label: "Terminal",     icon: Monitor         },
  { href: "/liquidity-map", label: "Liquidity Map",icon: Layers          },
  { href: "/whale-alerts",  label: "Whale Alerts", icon: Bell            },
  { href: "/paper-trading", label: "Paper Trading",icon: BookOpen        },
];

export function TopNav() {
  const pathname = usePathname();

  const [utc, setUtc] = useState<string | null>(null);
  useEffect(() => {
    const tick = () => setUtc(new Date().toISOString().slice(11, 19));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <nav className="sticky top-0 z-50 w-full">
      {/* Deep glass atmosphere — two-stop vertical gradient + noise-like grain */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#0d0f1a]/97 via-[#0b0c16]/95 to-[#090a12]/92 backdrop-blur-2xl" />
      {/* Subtle grain overlay for cinematic texture */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.025]"
        style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")", backgroundSize: "128px 128px" }}
      />
      {/* Machined top highlight */}
      <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
      {/* Bottom separator — stronger violet sweep */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-violet-500/40 to-cyan-400/15"
      />
      {/* Ambient violet under-glow spilling down */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-b from-violet-500/[0.06] to-transparent"
      />

      <div className="relative mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-[52px] items-center gap-3 sm:gap-5">

          {/* ── Brand block ──────────────────────────────────────────────────── */}
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-cyan-400/60"
          >
            {/* Mark tile — violet glass with animated outer glow on hover */}
            <span className="relative flex h-[28px] w-[28px] items-center justify-center rounded-[7px] border border-violet-400/35 bg-gradient-to-br from-violet-500/[0.28] via-violet-600/[0.14] to-cyan-400/[0.06] shadow-[inset_0_1px_0_rgba(255,255,255,0.10),0_0_18px_-5px_rgba(139,92,246,0.7)] transition-all duration-200 group-hover:border-violet-300/55 group-hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_0_24px_-4px_rgba(139,92,246,0.85),0_0_8px_-2px_rgba(139,92,246,0.4)]">
              <Activity className="h-3.5 w-3.5 text-violet-200 drop-shadow-[0_0_4px_rgba(196,181,253,0.7)]" strokeWidth={2.5} />
            </span>
            <span className="flex items-baseline gap-1.5">
              <span className="lm-brand text-[13.5px] tracking-[0.07em] text-white/90 drop-shadow-[0_0_10px_rgba(139,92,246,0.35)] transition-all duration-150 group-hover:text-white group-hover:drop-shadow-[0_0_14px_rgba(139,92,246,0.55)]">
                LUMORA
              </span>
              <span className="num hidden text-[8px] uppercase tracking-[0.28em] text-lm-muted md:inline">
                Terminal
              </span>
            </span>
          </Link>

          {/* ── Link rail ────────────────────────────────────────────────────── */}
          <div className="lm-no-scrollbar flex min-w-0 flex-1 items-center overflow-x-auto">
            {/* Recessed channel — deeper inset shadow than LM69C */}
            <div className="flex items-center gap-0 rounded-xl border border-white/[0.045] bg-black/30 p-[3px] shadow-[inset_0_2px_6px_rgba(0,0,0,0.55),inset_0_-1px_0_rgba(255,255,255,0.02),inset_0_0_0_1px_rgba(255,255,255,0.015)]">
              {navLinks.map(({ href, label, icon: Icon }) => {
                const isActive = pathname === href || pathname.startsWith(href + "/");
                return (
                  <Link
                    key={href}
                    href={href}
                    title={label}
                    className={clsx(
                      "group relative flex shrink-0 items-center gap-1.5 rounded-[9px] px-2.5 py-[7px] text-[12px] font-medium sm:px-3",
                      "transition-colors duration-100 ease-out",
                      "active:scale-[0.975] active:transition-transform",
                      "motion-reduce:transition-none motion-reduce:active:scale-100",
                      "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1 focus-visible:outline-cyan-400/60",
                      isActive ? "text-white" : "text-[#8892b0] hover:text-white/80",
                    )}
                  >
                    {/* Sliding active pill (layoutId — animates between tabs) */}
                    {isActive && (
                      <motion.span
                        layoutId="nav-active-pill"
                        className="pointer-events-none absolute inset-0 rounded-[9px]"
                        style={{
                          background: "linear-gradient(160deg, rgba(139,92,246,0.22) 0%, rgba(139,92,246,0.10) 60%, rgba(99,102,241,0.06) 100%)",
                          boxShadow: "inset 0 0 0 1px rgba(139,92,246,0.28), inset 0 1px 0 rgba(255,255,255,0.07)",
                        }}
                        transition={{ type: "spring", stiffness: 400, damping: 38 }}
                      />
                    )}

                    {/* Limelight — top-edge bar slides with active pill */}
                    {isActive && (
                      <motion.span
                        layoutId="nav-limelight"
                        aria-hidden
                        className="pointer-events-none absolute inset-x-2 top-0 h-px rounded-full"
                        style={{
                          background: "linear-gradient(90deg, transparent, rgba(139,92,246,0.9) 20%, rgba(196,181,253,1) 50%, rgba(139,92,246,0.9) 80%, transparent)",
                          boxShadow: "0 0 10px 1px rgba(139,92,246,0.5), 0 0 20px 2px rgba(139,92,246,0.25)",
                        }}
                        transition={{ type: "spring", stiffness: 400, damping: 38 }}
                      />
                    )}

                    {/* Hover radial bloom — quiet violet behind inactive links */}
                    {!isActive && (
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-0 rounded-[9px] bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,92,246,0.12),transparent_70%)] opacity-0 transition-opacity duration-200 group-hover:opacity-100 motion-reduce:transition-none"
                      />
                    )}

                    {/* Hover: 1px top shimmer on inactive */}
                    {!isActive && (
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-x-2 top-0 h-px rounded-full bg-white/0 transition-all duration-200 group-hover:bg-white/[0.07] motion-reduce:transition-none"
                      />
                    )}

                    <Icon
                      className={clsx(
                        "relative h-3.5 w-3.5 shrink-0 transition-colors duration-100 motion-reduce:transition-none",
                        isActive
                          ? "text-violet-300 drop-shadow-[0_0_6px_rgba(196,181,253,0.6)]"
                          : "text-[#4a5580] group-hover:text-[#8892b0]",
                      )}
                    />
                    <span className="relative hidden lg:inline">{label}</span>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* ── Status rail ──────────────────────────────────────────────────── */}
          <div className="ml-auto flex shrink-0 items-center">
            <div className="num relative flex items-center gap-2 overflow-hidden rounded-xl border border-white/[0.045] bg-black/30 px-3 py-[6px] shadow-[inset_0_2px_6px_rgba(0,0,0,0.55),inset_0_-1px_0_rgba(255,255,255,0.02)]">
              {/* Cyan ambient glow behind LIVE */}
              <span
                aria-hidden
                className="pointer-events-none absolute -right-2 -top-2 h-8 w-8 rounded-full bg-emerald-400/10 blur-lg"
              />
              {utc && (
                <>
                  <span className="relative hidden text-[10px] tracking-wide text-[#4a5580] md:inline">
                    {utc} <span className="text-[#2d3450]">UTC</span>
                  </span>
                  <span aria-hidden className="hidden h-3 w-px bg-white/[0.07] md:block" />
                </>
              )}
              <span className="relative flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.18em] text-emerald-300/95">
                <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.55),0_0_3px_rgba(52,211,153,0.9)]" />
                <span className="hidden sm:inline font-medium">Live</span>
              </span>
            </div>
          </div>

        </div>
      </div>
    </nav>
  );
}
