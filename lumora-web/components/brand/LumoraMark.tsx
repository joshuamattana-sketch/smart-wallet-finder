type Props = {
  size?: number;
  className?: string;
};

// Lumora brand mark: the "aperture" — two luminous arcs around a bright core.
// Reads as a lens / seeing the market clearly + light (lumen). Solid two-tone
// (violet + cyan) so it stays crisp from favicon size up. Server-safe, no defs,
// no gradient ids to collide. aria-hidden: the wordmark next to it names it.
export function LumoraMark({ size = 26, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <circle
        cx="50"
        cy="50"
        r="34"
        stroke="#8b5cf6"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray="150 64"
        transform="rotate(-50 50 50)"
      />
      <circle
        cx="50"
        cy="50"
        r="19"
        stroke="#22d3ee"
        strokeWidth="6"
        strokeLinecap="round"
        strokeDasharray="78 42"
        transform="rotate(120 50 50)"
      />
      <circle cx="50" cy="50" r="6.5" fill="#22d3ee" />
    </svg>
  );
}
