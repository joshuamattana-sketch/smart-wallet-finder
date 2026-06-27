// Always-moving selling-point ticker. Pure CSS marquee (no JS): the track holds
// the items twice and shifts left by half its width for a seamless loop. Pauses
// on hover. This is the "eyes eat first" motion that greets every visitor.
const ITEMS = [
  "XAUUSD · M15",
  "+85 pt per trade, net",
  "17,000+ trades scored",
  "No look-ahead",
  "Net of spread",
  "You place every trade",
  "Signals, not a black box",
  "Private early access",
];

function Row() {
  return (
    <>
      {ITEMS.map((t, i) => (
        <span key={`${t}-${i}`} className="flex items-center gap-6 whitespace-nowrap px-6">
          <span className="fx-num text-[12.5px] font-medium tracking-tight text-fintech-ink-soft">
            {t}
          </span>
          <span className="h-1 w-1 rounded-full bg-fintech-indigo" aria-hidden="true" />
        </span>
      ))}
    </>
  );
}

export function TickerStrip() {
  return (
    <div
      className="fx-marquee-group overflow-hidden border-b border-fintech-line-soft bg-white py-2.5"
      aria-hidden="true"
    >
      <div className="fx-marquee flex w-max">
        <Row />
        <Row />
      </div>
    </div>
  );
}
