/**
 * lumora-web/app/api/gold-bot/status/route.ts
 * ---------------------------------------------
 * LM91A — Local READ-ONLY Gold Bot status API.
 *
 * GET /api/gold-bot/status
 *   Server-side only. Reads local JSON artifacts from <repo_root>/data/gold_bot
 *   and returns one tolerant status object. NEVER calls MT5, never runs Python /
 *   shell, never makes external HTTP, never reads secrets / the Discord webhook
 *   env. Missing files → flags + warnings, never a crash.
 *
 * Marked dynamic so Next.js never pre-renders it at build time (deploys without
 * the local files must still serve the route).
 */

import { NextResponse } from "next/server";
import { loadGoldBotStatus } from "@/lib/gold-bot-status";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const status = await loadGoldBotStatus();
    return NextResponse.json(status, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    // The loader is engineered never to throw; the route stays uncrashable.
    return NextResponse.json(
      {
        ok: false,
        generatedAt: new Date().toISOString(),
        mode: "local_read_only",
        warnings: [`route error: ${(err as Error).message ?? "unknown"}`],
      },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  }
}
