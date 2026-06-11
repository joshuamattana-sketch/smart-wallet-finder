"use client";

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

  return (
    <nav className="lm-topnav sticky top-0 z-50 w-full">
      <div className="mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-12 items-center gap-6">
          {/* Brand */}
          <Link href="/" className="flex items-center gap-2 shrink-0 group">
            <Activity
              className="h-4 w-4 text-lm-purple transition-colors group-hover:text-purple-300"
              strokeWidth={2.5}
            />
            <span className="lm-brand text-[15px] text-lm-text">LUMORA</span>
          </Link>

          {/* Divider */}
          <div className="hidden sm:block h-5 w-px bg-lm-border shrink-0" />

          {/* Nav links — icon-only under lg, scrollable on tiny screens */}
          <div className="flex items-center gap-0.5 flex-1 min-w-0 overflow-x-auto lm-no-scrollbar">
            {navLinks.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  title={label}
                  className={clsx(
                    "lm-nav-link flex items-center gap-1.5 px-2 sm:px-2.5 py-1.5 rounded text-[13px] font-medium shrink-0",
                    isActive && "lm-nav-link-active",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="hidden lg:inline">{label}</span>
                </Link>
              );
            })}
          </div>

          {/* Right: single live status indicator (no badge clutter) */}
          <div className="ml-auto flex items-center gap-2 text-[11px] text-lm-text-dim num shrink-0">
            <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 text-emerald-400" />
            <span className="hidden sm:inline tracking-wide uppercase">Live</span>
          </div>
        </div>
      </div>
    </nav>
  );
}
