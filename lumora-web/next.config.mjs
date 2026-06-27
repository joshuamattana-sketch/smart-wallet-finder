/** @type {import('next').NextConfig} */

// Content-Security-Policy. Scoped to exactly what this app loads:
//   - scripts: self + Google Analytics loader (googletagmanager.com)
//   - connect (fetch/xhr/ws): self + Supabase (REST + realtime) + GA collect
//   - img: self + data URIs + GA pixels
//   - styles: self + inline (Tailwind utilities + framer-motion inline styles)
//   - fonts: self (next/font self-hosts) + data
// 'unsafe-inline' on script-src is required because Next's hydration bootstrap
// and the gtag init are inline. Moving to a per-request nonce is the hardening
// follow-up; it forces fully dynamic rendering, so it's deliberately deferred.
// frame-ancestors/object-src/base-uri/form-action lock down clickjacking,
// plugin abuse and form/base hijacking regardless.
//
// PROD ONLY. `next dev` needs 'unsafe-eval' (React Fast Refresh), a ws: HMR
// socket, and must NOT upgrade-insecure-requests (localhost is http, so the
// upgrade breaks every chunk/RSC fetch). Rather than ship a looser dev CSP,
// we send the strict CSP only in production builds; dev gets no CSP.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https://www.googletagmanager.com https://www.google-analytics.com",
  "font-src 'self' data:",
  "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://www.googletagmanager.com https://www.google-analytics.com https://*.google-analytics.com https://*.analytics.google.com",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

const isProd = process.env.NODE_ENV === "production";

// Baseline security headers applied to every response. CSP is production-only
// (see note above); the rest are harmless in dev and stay on everywhere.
const securityHeaders = [
  ...(isProd ? [{ key: "Content-Security-Policy", value: csp }] : []),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
