export const RECOVERY_EMAIL = "alhwez@gmail.com";
export const DEFAULT_PIN = "123456";
export const SESSION_COOKIE = "rizg_session";
export const PIN_SETUP_COOKIE = "rizg_pin_cfg";
export const PIN_MIN_LENGTH = 4;
export const PIN_MAX_LENGTH = 8;
export const SESSION_DAYS = 7;
export const RESET_MINUTES = 15;

export function authSecret(): string {
  return process.env.AUTH_SECRET?.trim() || "rizg-personal-gate-v1";
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
