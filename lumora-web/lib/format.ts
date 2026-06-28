// Locale-stable number formatting. `toLocaleString()` with no explicit locale
// uses the runtime's locale — on a German-locale server that renders USD as
// "$60.145,6" (period = thousands, comma = decimal), which looks broken on a
// trading terminal. These helpers pin en-US so numbers read the same
// everywhere, server or client.

function enUS(maxFrac: number): Intl.NumberFormat {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: 0,
  });
}

/** Plain grouped number, en-US. e.g. 60145.6 → "60,145.6". */
export function fmtNum(n: number, maxFrac = 2): string {
  return enUS(maxFrac).format(n);
}

/** USD with a leading $. e.g. 60145.6 → "$60,145.6". */
export function fmtUsd(n: number, maxFrac = 2): string {
  return "$" + enUS(maxFrac).format(n);
}
