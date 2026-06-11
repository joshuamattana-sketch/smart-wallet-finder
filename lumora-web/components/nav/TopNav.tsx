"use client";

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
    <nav className="lm-topnav sticky top-0 z-50 w-full">
      <div className="mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-12 items-center gap-5">
          {/* Brand */}
          <Link href="/" className="group flex shrink-0 items-baseline gap-2">
            <Activity
              className="h-4 w-4 self-center text-lm-purple transition-colors group-hover:text-purple-300"
              strokeWidth={2.5}
            />
            <span className="lm-brand text-[15px] text-lm-text">LUMORA</span>
            <span className="num hidden text-[9px] uppercase tracking-[0.22em] text-lm-muted md:inline">
              Terminal
            </span>
          </Link>

          {/* Divider */}
          <div className="hidden h-5 w-px shrink-0 bg-lm-border sm:block" />

          {/* Nav links — icon-only under lg, scrollable on tiny screens */}
          <div className="lm-no-scrollbar flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
            {navLinks.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  title={label}
                  className={clsx(
                    "lm-nav-link flex shrink-0 items-center gap-1.5 rounded px-2 py-1.5 text-[13px] font-medium sm:px-2.5",
                    "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-cyan-400/60",
                    isActive && "lm-nav-link-active",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="hidden lg:inline">{label}</span>
                </Link>
              );
            })}
          </div>

          {/* Right: UTC session clock + single live indicator */}
          <div className="ml-auto flex shrink-0 items-center gap-3">
            {utc && (
              <span className="num hidden text-[11px] tracking-wide text-lm-muted md:inline">
                {utc} UTC
              </span>
            )}
            <span className="num flex items-center gap-2 text-[11px] uppercase tracking-wide text-lm-text-dim">
              <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 text-emerald-400" />
              <span className="hidden sm:inline">Live</span>
            </span>
          </div>
        </div>
      </div>
    </nav>
  );
}
