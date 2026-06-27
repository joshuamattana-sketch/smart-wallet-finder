import { Star } from "lucide-react";

// PLACEHOLDER reviews. Swap these for real early-access feedback before launch.
// Fabricated reviews for a live commercial financial product are illegal in the
// EU/DE (UWG) and break trust if discovered, so treat this array as a template
// the moment real quotes exist.
type Review = { quote: string; name: string; role: string; initials: string };

const REVIEWS: Review[] = [
  {
    quote:
      "First signal service I have seen that leaves the losing trades in the average. I read the methodology before I trusted a single call.",
    name: "Marcus R.",
    role: "Swing trader, 6 years",
    initials: "MR",
  },
  {
    quote:
      "I run the guarded preset and place every trade myself. Watching the record update live is what made me stop second guessing it.",
    name: "Aleksandra P.",
    role: "Part-time trader",
    initials: "AP",
  },
  {
    quote:
      "No fast cars, no pressure, no black box. Just numbers I could check. After years of hyped bots that is rare.",
    name: "David K.",
    role: "Gold trader",
    initials: "DK",
  },
];

export function Reviews() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {REVIEWS.map((r) => (
        <figure
          key={r.name}
          className="flex flex-col rounded-2xl border border-fintech-line-soft bg-white p-6"
        >
          <div className="flex gap-0.5 text-fintech-indigo" aria-label="5 out of 5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Star key={i} className="h-4 w-4 fill-current" aria-hidden="true" />
            ))}
          </div>
          <blockquote className="mt-4 flex-1 text-[14.5px] leading-[1.7] text-fintech-ink">
            {r.quote}
          </blockquote>
          <figcaption className="mt-5 flex items-center gap-3 border-t border-fintech-line-soft pt-4">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-fintech-indigo-soft text-[12px] font-medium text-fintech-indigo-ink">
              {r.initials}
            </span>
            <span>
              <span className="block text-[13.5px] font-medium text-fintech-ink">{r.name}</span>
              <span className="block text-[12px] text-fintech-muted">{r.role}</span>
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
