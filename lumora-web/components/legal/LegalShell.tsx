import Link from "next/link";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import { LumoraMark } from "@/components/brand/LumoraMark";
import { SiteFooter } from "@/components/ui/SiteFooter";
import { LEGAL_DETAILS_FILLED, LEGAL_LAST_UPDATED } from "@/lib/site";

// LM77A — shared frame for Impressum / Datenschutz / Risk. Deliberately reads at
// a comfortable 15–16px (legal text must be readable, unlike the dense terminal
// chrome). Shows a loud placeholder banner until the operator fills real details.
type Props = {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
};

export function LegalShell({ title, subtitle, children }: Props) {
  return (
    <div className="flex min-h-screen flex-col bg-lm-bg">
      <header className="border-b border-lm-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <LumoraMark size={24} />
            <span className="lm-brand text-[15px] text-lm-text">Lumora</span>
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-[13px] text-lm-text-dim transition-colors hover:text-lm-text"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to site
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10 sm:px-6 sm:py-14">
        {!LEGAL_DETAILS_FILLED && (
          <div
            role="note"
            className="mb-8 flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-[13px] leading-relaxed text-amber-200"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none text-amber-400" />
            <span>
              <strong className="font-semibold">Placeholder, not yet live.</strong> The operator
              details on this page are placeholders. Fill them in <code className="text-amber-300">lib/site.ts</code>{" "}
              and set <code className="text-amber-300">LEGAL_DETAILS_FILLED = true</code> before
              release. This notice disappears once done. (Template only, have it reviewed by a
              lawyer.)
            </span>
          </div>
        )}

        <p className="num text-[11px] uppercase tracking-[0.22em] text-lm-muted">Legal</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-lm-text sm:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-2 text-[15px] leading-relaxed text-lm-text-dim">{subtitle}</p>}

        <div className="lm-legal-prose mt-8">{children}</div>

        <p className="mt-12 text-[12px] text-lm-muted">Last updated: {LEGAL_LAST_UPDATED}</p>
      </main>

      <SiteFooter variant="full" />
    </div>
  );
}
