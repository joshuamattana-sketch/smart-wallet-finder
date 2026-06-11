import { PageTransition } from "@/components/ui/PageTransition";

// ── PageShell (LM69B) ────────────────────────────────────────────────────────
// The one page skeleton: standardized header (title + context line + a
// right-hand slot for status chips or page controls) and a fixed vertical
// rhythm for sections. Replaces the five hand-rolled per-page headers.
//
// Conventions:
//   - `status` holds AT MOST the page's toolbar + 1–2 status chips.
//   - Sections inside `children` should not add their own outer margins —
//     the shell owns the rhythm (12px between sections).

interface PageShellProps {
  title: React.ReactNode;
  /** One quiet line under the title. Keep it to a single clause. */
  context?: React.ReactNode;
  /** Right-aligned header slot: page controls and/or ≤2 status chips. */
  status?: React.ReactNode;
  children: React.ReactNode;
}

export function PageShell({ title, context, status, children }: PageShellProps) {
  return (
    <PageTransition className="space-y-3">
      <header className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2 border-b border-lm-border/60 pb-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 text-lg font-semibold leading-tight tracking-tight text-lm-text">
            {title}
          </h1>
          {context ? (
            <p className="mt-0.5 text-[11px] leading-snug text-lm-muted">{context}</p>
          ) : null}
        </div>
        {status ? (
          <div className="flex flex-wrap items-center gap-2">{status}</div>
        ) : null}
      </header>
      {children}
    </PageTransition>
  );
}
