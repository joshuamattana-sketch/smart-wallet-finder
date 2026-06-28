import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { ACCESS_COOKIE, verifyAccessToken } from "@/lib/access";

// LM76A — gate every private-beta surface behind a valid access cookie.
// Pages without a valid cookie → redirect to /enter (the invite-code page).
// App data APIs without a valid cookie → 401 JSON (a redirect would hand HTML
// back to a fetch()). /enter and /api/beta-unlock are intentionally NOT matched
// so a visitor can actually reach the gate and redeem a code.
export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const token = req.cookies.get(ACCESS_COOKIE)?.value;
  if (await verifyAccessToken(token)) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = req.nextUrl.clone();
  url.pathname = "/enter";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: [
    // ── Gated pages ──────────────────────────────────────────────────────
    "/dashboard",
    "/dashboard/:path*",
    "/terminal",
    "/terminal/:path*",
    "/liquidity-map",
    "/liquidity-map/:path*",
    "/whale-alerts",
    "/whale-alerts/:path*",
    "/paper-trading",
    "/paper-trading/:path*",
    // ── Gated app data APIs (these are only ever called by the gated pages;
    //    no public page touches them, so the cookie requirement is safe) ───
    "/api/heatmap",
    "/api/heatmap/:path*",
    "/api/whale-alerts",
    "/api/whale-alerts/:path*",
  ],
};
