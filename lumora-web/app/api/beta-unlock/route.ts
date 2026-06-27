import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { ACCESS_COOKIE, signAccessToken, cookieMaxAgeSeconds } from "@/lib/access";
import { isRateLimited, clientIp } from "@/lib/rate-limit";

// LM76A — redeem an invite code and, on success, set the signed access cookie.
// Validation runs through the SECURITY DEFINER redeem_invite_code() RPC, so the
// invite_codes table is never exposed to the client.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Invite codes are the only thing standing between the public and the app, so
// the redeem endpoint is the brute-force target. Cap attempts per IP.
const RL_MAX = 10;
const RL_WINDOW_MS = 10 * 60 * 1000;

// Builds the success response with the signed, httpOnly access cookie.
async function grantAccess(): Promise<NextResponse> {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(ACCESS_COOKIE, await signAccessToken(), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: cookieMaxAgeSeconds(),
  });
  return res;
}

export async function POST(req: Request) {
  const ip = clientIp(req.headers);
  if (isRateLimited(`beta-unlock:${ip}`, RL_MAX, RL_WINDOW_MS)) {
    return NextResponse.json(
      { ok: false, error: "Too many attempts. Please try again later." },
      { status: 429 },
    );
  }

  const body = (await req.json().catch(() => null)) as { code?: unknown } | null;
  const code = String(body?.code ?? "").trim();
  if (!code || code.length > 64) {
    return NextResponse.json({ ok: false, error: "Enter your invite code." }, { status: 400 });
  }

  // Owner master code (env-only secret). Checked before the DB so the owner can
  // always get in — even while the invite DB is unavailable. Must be a strong,
  // private value; never commit a real one. Disabled unless set to >=12 chars.
  const ownerCode = process.env.LUMORA_OWNER_CODE;
  if (ownerCode && ownerCode.length >= 12 && code === ownerCode) {
    return grantAccess();
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    return NextResponse.json({ ok: false, error: "Access isn't configured yet." }, { status: 500 });
  }

  const supabase = createClient(url, key, { auth: { persistSession: false } });
  const { data, error } = await supabase.rpc("redeem_invite_code", { p_code: code });
  if (error || data !== true) {
    return NextResponse.json(
      { ok: false, error: "That code is invalid or fully used." },
      { status: 401 },
    );
  }

  return grantAccess();
}
