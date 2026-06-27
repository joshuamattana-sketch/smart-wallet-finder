import { ChevronDown } from "lucide-react";

type QA = { q: string; a: string };

// Native details/summary accordion: accessible, keyboard-operable, zero client JS.
// Answers are blunt and honest, no spin, matching the transparency thesis.
const ITEMS: QA[] = [
  {
    q: "Is this financial advice?",
    a: "No. Meridian gives you information and rules-based signals, not advice. It describes a strategy and its results and never tells you to buy or sell. Every trade is your own decision and your own risk.",
  },
  {
    q: "A 30% win rate sounds bad. Why would I want that?",
    a: "Because win rate is the wrong scoreboard here. The strategy holds winners on time so they land bigger than the losers. Across 17,000+ trades the average comes out positive net of spread. We hold a few big winners against many small losers, and we show the win rate openly instead of hiding it.",
  },
  {
    q: "Will it auto-trade my account or take a cut?",
    a: "No. Meridian sends signals only: an entry, a stop, and the exit logic. You place every trade yourself at your own broker. We never connect to, control, or touch your funds.",
  },
  {
    q: "Every bot shows a perfect backtest. Why is yours different?",
    a: "Because of how it is graded. No look-ahead, so every call uses only what was on the screen at that bar. Spread is taken off before any number reaches the page. Losing trades stay in the average, and the sample is 17,000+ trades rather than a lucky month.",
  },
  {
    q: "The pure swing has no stop loss. Is that safe?",
    a: "It carries open risk on each trade until it closes, which is why the guarded swing is the default pick: it keeps a wide protective stop so one bad move cannot run away. You choose which version to run, on purpose.",
  },
  {
    q: "Why no testimonials or user counts?",
    a: "Because we would have to invent them, and that is exactly the behaviour that burned you. We are in private early access and choose to earn trust from the methodology and the transparent track record instead.",
  },
  {
    q: "What does it cost?",
    a: "Early access is free, no card and nothing to cancel. You leave an email and get an invite when a spot opens. The trading decision always stays yours.",
  },
];

export function FintechFaq() {
  return (
    <div className="divide-y divide-fintech-line-soft rounded-2xl border border-fintech-line-soft bg-white">
      {ITEMS.map((item) => (
        <details key={item.q} className="group px-5">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 text-[15px] font-medium text-fintech-ink [&::-webkit-details-marker]:hidden">
            {item.q}
            <ChevronDown
              className="h-4 w-4 shrink-0 text-fintech-faint transition-transform duration-200 group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <p className="pb-4 pr-8 text-[14px] leading-[1.7] text-fintech-ink-soft">{item.a}</p>
        </details>
      ))}
    </div>
  );
}
