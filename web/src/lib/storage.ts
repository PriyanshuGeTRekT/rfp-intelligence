// localStorage that never throws (private windows, blocked storage).

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown): void {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable: the setting lasts for this page view only
  }
}

export const KEYS = {
  apiKey: "rfp.apiKey",
  theme: "rfp.theme",
  conversation: "rfp.conversation",
} as const;
