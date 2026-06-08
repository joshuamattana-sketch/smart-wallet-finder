/**
 * lumora-web/app/api/whale-alerts/route.ts
 * -----------------------------------------
 * LM63F — Local whale alerts API.
 *
 * GET /api/whale-alerts
 *   Optional query: ?limit=50
 *
 * Returns the local LM63E JSONL journal when available, else falls back
 * to the in-repo mock alerts. Always JSON. Never throws.
 *
 * Marked dynamic so Next.js never tries to pre-render this at build time —
 * Vercel deploys without the local journal must still serve the route.
 */

import { NextResponse } from "next/server";
import { loadWhaleAlerts } from "@/lib/whale-alerts-loader";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_LIMIT = 50;

export async function GET(req: Request) {
  let limit = DEFAULT_LIMIT;
  try {
    const url = new URL(req.url);
    const raw = url.searchParams.get("limit");
    if (raw) {
      const parsed = Number.parseInt(raw, 10);
      if (Number.isFinite(parsed) && parsed > 0) limit = parsed;
    }
  } catch {
    // Bad URL parse — defensively keep the default.
  }

  try {
    const payload = await loadWhaleAlerts(limit);
    return NextResponse.json(payload, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    // The loader is engineered to never throw, but the route must still
    // be uncrashable.
    return NextResponse.json(
      {
        data_source: "mock",
        generated_at: new Date().toISOString(),
        journal_row_count: 0,
        alerts: [],
        note: `route handler error: ${(err as Error).message ?? "unknown"}`,
      },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  }
}
