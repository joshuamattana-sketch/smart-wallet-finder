"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { Activity, LayoutDashboard, Monitor, Layers, Bell, BookOpen } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

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
    <nav className="sticky top-0 z-50 w-full border-b border-lumora-border bg-lumora-bg/80 backdrop-blur-xl">
      <div className="mx-auto max-w-screen-2xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center gap-6">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <Activity className="h-5 w-5 text-lumora-purple" strokeWidth={2.5} />
            <span className="text-lg font-semibold tracking-tight">
              <span className="text-neon-purple">Lumora</span>
            </span>
          </Link>

          {/* Nav links */}
          <div className="hidden md:flex items-center gap-1 flex-1">
            {navLinks.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150",
                  pathname === href || pathname.startsWith(href + "/")
                    ? "bg-lumora-purple/20 text-lumora-purple-bright"
                    : "text-lumora-text-dim hover:text-lumora-text hover:bg-lumora-surface"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </Link>
            ))}
          </div>

          {/* Right */}
          <div className="ml-auto flex items-center gap-3">
            <Badge variant="purple">
              <span className="mr-1 h-1.5 w-1.5 rounded-full bg-purple-400 animate-pulse inline-block" />
              Private Beta
            </Badge>
          </div>
        </div>
      </div>
    </nav>
  );
}
