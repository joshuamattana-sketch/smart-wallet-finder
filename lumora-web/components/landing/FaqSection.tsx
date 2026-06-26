import { ChevronDown } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";

// LM78A (CRO) — objection handling. The landing scored 0/100 on the audit's
// "trust & objections" dimension because there was nowhere that answered the
// five questions a skeptical first-time trader actually asks. Native
// <details>/<summary> = accessible, keyboard-operable, zero client JS.

type Qa = { q: string; a: React.ReactNode };

const FAQ: Qa[] = [
  {
    q: "What exactly is Lumora?",
    a: "A liquidity-intelligence terminal. It reads the order book, whale trades and futures positioning, then turns all of it into one plain market read (bias, score, risk) instead of another wall of charts.",
  },
  {
    q: "Is this financial advice?",
    a: "No. Lumora describes market structure for information only. It does not predict prices and never tells you to buy or sell. Always do your own research.",
  },
  {
    q: "Is it free?",
    a: "Free during the private beta. We onboard in small waves to keep feedback tight, so leave your email and we'll send an invite when your spot opens.",
  },
  {
    q: "Where does the data come from?",
    a: "Live exchange order-book and trade feeds (Binance spot + futures). During beta some surfaces show clearly-labeled demo data while live integrations roll out. Nothing fake is ever shown as live.",
  },
  {
    q: "Do I need an invite code?",
    a: "The terminal is invite-only during beta. No code yet? Join the waitlist and we'll send you one. You don't need a code to get on the list.",
  },
  {
    q: "What makes it different?",
    a: "No paid 'calls', no black box you're just told to trust. Just the raw order flow, turned into one line you can act on, with every demo surface labeled honestly.",
  },
];

export function FaqSection() {
  return (
    <section className="px-4 py-9" aria-labelledby="faq-heading">
      <div className="mx-auto max-w-3xl">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <span className="lm-section-title">06 · Questions</span>
            <h2 id="faq-heading" className="lm-display mt-2 text-xl font-semibold tracking-tight text-lm-text">
              No black box. Ask the obvious questions.
            </h2>
          </div>
          <StatusBadge variant="neutral" size="sm">
            Honest by default
          </StatusBadge>
        </div>

        <div className="divide-y divide-lm-border overflow-hidden rounded-lg border border-lm-border bg-lm-surface">
          {FAQ.map((item) => (
            <details key={item.q} className="group">
              <summary className="lm-row flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3.5 text-[14px] font-medium text-lm-text [&::-webkit-details-marker]:hidden">
                {item.q}
                <ChevronDown className="h-4 w-4 flex-none text-lm-muted transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <p className="px-4 pb-4 text-[13px] leading-relaxed text-lm-text-dim">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
