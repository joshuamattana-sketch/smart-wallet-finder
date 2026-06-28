import "server-only";
import crypto from "node:crypto";

// LM79A — owner-only session for /admin. Separate from the beta access cookie
// (lib/access.ts): the payload is namespaced "admin." so a beta cookie can never
// be replayed as an admin one. Signed with LUMORA_ACCESS_SECRET; the owner
// authenticates with LUMORA_OWNER_CODE (the same skeleton key used at /enter).

export const ADMIN_COOKIE = "lumora_admin";
const TTL_MS = 1000 * 60 * 60 * 12; // 12-hour admin session

function secret(): string {
  return process.env.LUMORA_ACCESS_SECRET ?? "";
}

function ownerCode(): string {
  return process.env.LUMORA_OWNER_CODE ?? "";
}

// Both pieces must be present (and the owner code non-trivial) for admin to work.
export function adminConfigured(): boolean {
  return ownerCode().length >= 12 && secret().length > 0;
}

function hmacHex(message: string): string {
  return crypto.createHmac("sha256", secret()).update(message).digest("hex");
}

export function checkOwnerCode(code: string): boolean {
  const oc = ownerCode();
  if (oc.length < 12) return false;
  const a = Buffer.from(code);
  const b = Buffer.from(oc);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

export function signAdminToken(): string {
  const exp = Date.now() + TTL_MS;
  return `${exp}.${hmacHex(`admin.${exp}`)}`;
}

export function verifyAdminToken(token: string | undefined): boolean {
  if (!token || !secret()) return false;
  const dot = token.indexOf(".");
  if (dot < 0) return false;
  const exp = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expNum = Number(exp);
  if (!Number.isFinite(expNum) || Date.now() > expNum) return false;
  const expected = hmacHex(`admin.${exp}`);
  if (sig.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
}

export function adminCookieMaxAge(): number {
  return Math.floor(TTL_MS / 1000);
}
