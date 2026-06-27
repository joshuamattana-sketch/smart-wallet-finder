// LM80A — best-effort in-memory IP rate limiter.
//
// Per server instance only (not shared across serverless lambdas), so it is not
// a hard global guarantee — but it blunts brute-force and spam without extra
// infra (Redis/Upstash would make it global; that's the upgrade path). Used by
// the invite-redeem endpoint and the waitlist.

type Timestamps = number[];
const buckets = new Map<string, Timestamps>();

/**
 * Returns true when `key` has exceeded `max` hits inside `windowMs` (i.e. the
 * caller should reject). Records the hit when allowed.
 */
export function isRateLimited(key: string, max: number, windowMs: number): boolean {
  const now = Date.now();
  const recent = (buckets.get(key) ?? []).filter((t) => now - t < windowMs);
  if (recent.length >= max) {
    buckets.set(key, recent);
    return true;
  }
  recent.push(now);
  buckets.set(key, recent);
  return false;
}

/** First hop of x-forwarded-for, or "unknown" behind a proxy that strips it. */
export function clientIp(headers: Headers): string {
  return (headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
}
