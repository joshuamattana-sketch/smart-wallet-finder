import Link from "next/link";
import { BOT_BRAND, BOT_RISK_NOTE } from "@/lib/bot-brand";
import { LEGAL_LINKS } from "@/lib/site";

// Slim light footer for the bot brand. Carries the risk disclaimer prominently —
// essential for a trading-signal product.
export function FintechFooter() {
  return (
    <footer className="border-t border-fintech-line-soft bg-fintech-mist">
      <div className="mx-auto max-w-6xl px-5 py-12">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Link href={BOT_BRAND.signalsHref} className="flex items-center gap-2.5">
            <span className="h-5 w-5 rounded-md bg-fintech-indigo" aria-hidden="true" />
            <span className="text-sm font-medium text-fintech-ink">{BOT_BRAND.name}</span>
          </Link>
          <nav aria-label="Legal" className="flex flex-wrap gap-5 text-[13px] text-fintech-muted">
            {LEGAL_LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="transition-colors hover:text-fintech-ink">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>

        <p className="mt-8 max-w-3xl text-[12px] leading-relaxed text-fintech-faint">
          {BOT_RISK_NOTE}
        </p>
        <p className="mt-4 text-[12px] text-fintech-faint">
          © {BOT_BRAND.name}. A research and analytics product. Not a broker, and not an execution
          venue.
        </p>
      </div>
    </footer>
  );
}
