export function qs(params?: Record<string, unknown>): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") sp.append(key, String(value));
  }
  const out = sp.toString();
  return out ? `?${out}` : "";
}
