import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { ACCESS_COOKIE, verifyAccessToken } from "@/lib/access";

// LM76A — gate the private-beta app routes behind a valid access cookie.
// No cookie / invalid / expired → redirect to /enter (the invite-code page).
export async function middleware(req: NextRequest) {
  const token = req.cookies.get(ACCESS_COOKIE)?.value;
  if (await verifyAccessToken(token)) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/enter";
  url.searchParams.set("next", req.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: [
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
    "/gold-bot",
    "/gold-bot/:path*",
  ],
};
