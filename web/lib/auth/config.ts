import {
  AUTH_VERSION,
  CLIENT_BUILD,
  PIN_MAX_LENGTH,
  PIN_MIN_LENGTH,
  RECOVERY_EMAIL,
  RESET_MINUTES,
  SESSION_DAYS,
} from "./public-constants";

export {
  AUTH_VERSION,
  CLIENT_BUILD,
  PIN_MAX_LENGTH,
  PIN_MIN_LENGTH,
  RECOVERY_EMAIL,
  RESET_MINUTES,
  SESSION_DAYS,
};

export const DEFAULT_PIN = "123456";
export const SESSION_COOKIE = `rizg_session_v${AUTH_VERSION}`;
export const PIN_SETUP_COOKIE = `rizg_pin_cfg_v${AUTH_VERSION}`;

const FALLBACK_SECRET = "rizg-personal-gate-v1";

export function authSecret(): string {
  const fromEnv = process.env.AUTH_SECRET?.trim();
  return fromEnv || FALLBACK_SECRET;
}

export function defaultAccessPin(): string {
  return process.env.ACCESS_PIN?.trim() || DEFAULT_PIN;
}

export function normalizePin(value: string): string {
  const arabic = "٠١٢٣٤٥٦٧٨٩";
  const mapped = value.replace(/[٠-٩]/g, (digit) => String(arabic.indexOf(digit)));
  return mapped.replace(/\D/g, "");
}

export function isValidPin(value: string): boolean {
  const pin = normalizePin(value);
  return pin.length >= PIN_MIN_LENGTH && pin.length <= PIN_MAX_LENGTH;
}

export function isRecoveryEmail(value: string): boolean {
  return value.trim().toLowerCase() === RECOVERY_EMAIL;
}
