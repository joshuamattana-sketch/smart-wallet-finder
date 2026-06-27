import Link from "next/link";
import { BOT_BRAND } from "@/lib/bot-brand";
import { ProductSwitch } from "./ProductSwitch";

// Serious light nav for the Meridian (bot) brand. The product switch is pinned
// dead-center of the bar so it sits in the exact same spot as on the Lumora
// nav — switching never moves the control, it only flips the active side.
export function FintechNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-fintech-line-soft bg-white/85 backdrop-blur-md">
      <div className="relative mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href={BOT_BRAND.signalsHref} className="flex items-center gap-2.5">
          <span
            className="grid h-7 w-7 place-items-center rounded-[9px] bg-fintech-ink"
            aria-hidden="true"
          >
            <span className="h-2.5 w-2.5 rounded-sm bg-fintech-indigo" />
          </span>
          <span className="text-[15px] font-medium tracking-tight text-fintech-ink">
            {BOT_BRAND.name}
          </span>
        </Link>

        {/* Centered, position-stable across both brands */}
        <div className="pointer-events-none absolute inset-0 hidden items-center justify-center sm:flex">
          <nav aria-label="Switch product" className="pointer-events-auto">
            <ProductSwitch active="signals" />
          </nav>
        </div>

        <a
          href="#early-access"
          className="fx-lift rounded-lg bg-fintech-ink px-4 py-2 text-[13px] font-medium text-white hover:shadow-[0_8px_20px_-8px_rgba(15,23,42,0.5)]"
        >
          Early access
        </a>
      </div>
    </header>
  );
}
