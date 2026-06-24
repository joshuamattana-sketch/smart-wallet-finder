// LM76A — signed access cookie for the invite-code gate. HMAC-SHA256 over an
// expiry timestamp, verifiable in both edge middleware and the node API route
// via Web Crypto (no node-only APIs here). The cookie proves "redeemed a valid
// invite", not which code — codes are consumed once at /enter.

export const ACCESS_COOKIE = "lumora_access";
const TTL_MS = 1000 * 60 * 60 * 24 * 30; // 30 days

function secret(): string {
  return process.env.LUMORA_ACCESS_SECRET ?? "";
}

async function hmacHex(message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function signAccessToken(): Promise<string> {
  const exp = Date.now() + TTL_MS;
  return `${exp}.${await hmacHex(String(exp))}`;
}

export async function verifyAccessToken(token: string | undefined): Promise<boolean> {
  if (!token || !secret()) return false;
  const dot = token.indexOf(".");
  if (dot < 0) return false;
  const exp = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expNum = Number(exp);
  if (!Number.isFinite(expNum) || Date.now() > expNum) return false;
  const expected = await hmacHex(exp);
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export function cookieMaxAgeSeconds(): number {
  return Math.floor(TTL_MS / 1000);
}
