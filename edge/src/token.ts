/**
 * Verifies ChampMail tracking tokens. Mirrors backend/app/services/tracking.py exactly:
 *   token = base64url(json) "." base64url(HMAC-SHA256(TRACKING_SECRET, "champmail-tracking-v1." + base64url(json)))
 * Do not change one side without the other; edge/test/fixtures/tokens.json (written by the Python signer) pins both.
 */
export interface Claim {
  message_id: string;
  domain_id: string;
  url: string | null;
}

const enc = new TextEncoder();

function b64u(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64u(s: string): Uint8Array {
  const std = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(std + "=".repeat((4 - (std.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function mac(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret.trim()), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64u(new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode("champmail-tracking-v1." + body))));
}

function sameString(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Python's is_http_url: http(s) scheme and a non-empty host. */
export function isHttpUrl(u: string): boolean {
  return /^https?:\/\/[^/?#\s]+/i.test(u);
}

/** The claim for a genuine token of this kind, else null. Never throws. */
export async function verify(secret: string | undefined, token: string, kind: "o" | "c" | "u"): Promise<Claim | null> {
  try {
    if (!secret?.trim()) return null; // an unset secret must reject everything, not sign with ""
    const parts = token.split(".");
    if (parts.length !== 2) return null;
    const [body, sig] = parts;
    if (!sameString(sig, await mac(secret, body))) return null;
    const d = JSON.parse(new TextDecoder().decode(fromB64u(body)));
    if (d.k !== kind || typeof d.m !== "string" || !d.m || typeof d.d !== "string" || !d.d) return null;
    const url = d.u ?? null;
    if ((kind === "c") !== (typeof url === "string" && url !== "")) return null;
    if (url !== null && (typeof url !== "string" || !isHttpUrl(url))) return null;
    return { message_id: d.m, domain_id: d.d, url };
  } catch {
    return null; // malformed base64, bad JSON, wrong types: all the same answer
  }
}
