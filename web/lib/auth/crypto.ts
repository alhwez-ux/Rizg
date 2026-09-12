import { authSecret } from "./config";

const encoder = new TextEncoder();

function toBytes(input: ArrayBuffer | Uint8Array): Uint8Array {
  return input instanceof Uint8Array ? input : new Uint8Array(input);
}

function toHex(input: ArrayBuffer | Uint8Array): string {
  return Array.from(toBytes(input), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function fromHex(hex: string): Uint8Array {
  const clean = hex.length % 2 === 0 ? hex : `0${hex}`;
  const bytes = new Uint8Array(clean.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

async function hmacKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", encoder.encode(authSecret()), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
}

export async function signValue(value: string): Promise<string> {
  const signature = await crypto.subtle.sign("HMAC", await hmacKey(), encoder.encode(value));
  return `${value}.${toHex(signature)}`;
}

export async function verifySigned(token: string): Promise<string | null> {
  const split = token.lastIndexOf(".");
  if (split <= 0) return null;
  const value = token.slice(0, split);
  const sig = token.slice(split + 1).trim().toLowerCase();
  if (!/^[0-9a-f]+$/.test(sig)) return null;
  try {
    // Edge runtimes often reject HMAC verify(); sign + compare is portable.
    const signature = await crypto.subtle.sign("HMAC", await hmacKey(), encoder.encode(value));
    const expected = toHex(signature);
    if (expected.length !== sig.length) return null;
    let diff = 0;
    for (let i = 0; i < expected.length; i += 1) {
      diff |= expected.charCodeAt(i) ^ sig.charCodeAt(i);
    }
    return diff === 0 ? value : null;
  } catch {
    return null;
  }
}

export async function hashSecret(secret: string, saltHex?: string): Promise<{ hash: string; salt: string }> {
  const salt = saltHex ? Uint8Array.from(fromHex(saltHex)) : crypto.getRandomValues(new Uint8Array(16));
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: Uint8Array.from(salt), iterations: 120_000 },
    key,
    256,
  );
  return { hash: toHex(bits), salt: toHex(salt) };
}

export async function verifySecret(secret: string, hash: string, salt: string): Promise<boolean> {
  const next = await hashSecret(secret, salt);
  if (next.hash.length !== hash.length) return false;
  let diff = 0;
  for (let i = 0; i < hash.length; i += 1) diff |= hash.charCodeAt(i) ^ next.hash.charCodeAt(i);
  return diff === 0;
}

export function randomCode(length = 6): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (byte) => String(byte % 10)).join("").slice(0, length);
}
