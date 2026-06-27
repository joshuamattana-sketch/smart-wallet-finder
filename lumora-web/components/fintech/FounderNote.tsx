// A human face behind the product. An anonymous signal service reads as a scam;
// one person putting their name to it reads as accountable. First-person, plain,
// no marketing voice. PLACEHOLDER name/initials: swap for the real founder name
// (and ideally a real photo) before launch.
const FOUNDER = { name: "Josh", role: "Founder", initials: "J" };

export function FounderNote() {
  return (
    <figure className="mx-auto max-w-3xl rounded-2xl border border-fintech-line-soft bg-white p-8 shadow-[0_2px_4px_rgba(15,23,42,0.04),0_24px_56px_-32px_rgba(15,23,42,0.22)] sm:p-10">
      <blockquote className="text-[clamp(1.15rem,1rem+0.6vw,1.45rem)] font-medium leading-[1.55] tracking-[-0.01em] text-fintech-ink">
        I am not a fund. I am one person who got tired of gold bots that show a perfect week and
        hide the rest. So I built the thing I wanted to see. One strategy, tested across years of
        gold, graded with no look-ahead and net of spread, with the losing trades left in, and it
        held up out of sample. I trade the guarded version myself while the live record builds. If
        the edge ever stops working, you will see it on this same page, because I am not going to
        hide it.
      </blockquote>
      <figcaption className="mt-7 flex items-center gap-3.5">
        <span className="grid h-11 w-11 place-items-center rounded-full bg-fintech-ink text-[15px] font-medium text-white">
          {FOUNDER.initials}
        </span>
        <span>
          <span className="block text-[14px] font-medium text-fintech-ink">{FOUNDER.name}</span>
          <span className="block text-[12.5px] text-fintech-muted">{FOUNDER.role}, Meridian</span>
        </span>
      </figcaption>
    </figure>
  );
}
