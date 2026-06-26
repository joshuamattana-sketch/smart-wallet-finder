import Link from "next/link";
import { Activity, MessageCircle } from "lucide-react";
import { DISCORD_URL, LEGAL_LINKS } from "@/lib/site";

// LM77A — one footer for every surface. `full` is the marketing footer on the
// landing + legal pages; `slim` is the persistent anchor inside the gated app,
// carrying the legal links and the "not financial advice" line on every screen.
type Props = { variant?: "full" | "slim" };

function LegalLinks({ className }: { className?: string }) {
  return (
    <nav aria-label="Legal" className={className}>
      {LEGAL_LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="text-lm-text-dim transition-colors hover:text-lm-text"
        >
          {l.label}
        </Link>
      ))}
    </nav>
  );
}

export function SiteFooter({ variant = "full" }: Props) {
  if (variant === "slim") {
    return (
      <footer className="border-t border-lm-border px-4 py-4">
        <div className="mx-auto flex max-w-screen-2xl flex-col items-center justify-between gap-2 sm:flex-row">
          <p className="text-[12px] text-lm-muted">
            Informational market context only · not financial advice · demo data during beta.
          </p>
          <div className="flex items-center gap-4 text-[12px]">
            <LegalLinks className="flex items-center gap-4" />
            <span className="text-lm-muted">© 2026 Lumora</span>
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer className="border-t border-lm-border px-4 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-lm-purple" />
            <span className="lm-brand text-sm text-lm-text">Lumora</span>
            <span className="ml-2 text-[13px] text-lm-muted">Liquidity intelligence terminal</span>
          </div>
          <div className="flex items-center gap-4 text-[13px]">
            <LegalLinks className="flex items-center gap-4" />
            <a
              href={DISCORD_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-lm-text-dim transition-colors hover:text-lm-cyan"
            >
              <MessageCircle className="h-3.5 w-3.5" />
              Discord
            </a>
          </div>
        </div>
        <div className="flex flex-col items-center justify-between gap-2 border-t border-lm-border/60 pt-4 sm:flex-row">
          <p className="text-[12px] leading-relaxed text-lm-muted">
            © 2026 Lumora. Informational market context only. No guaranteed outcomes, and not financial advice.
          </p>
          <p className="num text-[10px] uppercase tracking-[0.18em] text-lm-muted/80">
            Private beta · demo data shown
          </p>
        </div>
      </div>
    </footer>
  );
}
