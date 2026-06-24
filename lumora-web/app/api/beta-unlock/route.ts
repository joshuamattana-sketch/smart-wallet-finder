import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { ACCESS_COOKIE, signAccessToken, cookieMaxAgeSeconds } from "@/lib/access";

// LM76A — redeem an invite code and, on success, set the signed access cookie.
// Validation runs through the SECURITY DEFINER redeem_invite_code() RPC, so the
// invite_codes table is never exposed to the client.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { code?: unknown } | null;
  const code = String(body?.code ?? "").trim();
  if (!code || code.length > 64) {
    return NextResponse.json({ ok: false, error: "Enter your invite code." }, { status: 400 });
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
