export function logRequest(entry: { tool: string; method: string; url: string; status?: number; ms: number }) {
  try {
    const url = new URL(entry.url);
    for (const key of url.searchParams.keys()) {
      if (/key|token|secret|password/i.test(key)) url.searchParams.set(key, "REDACTED");
    }
    console.error(JSON.stringify({ ...entry, url: url.toString() }));
  } catch {
    console.error(JSON.stringify(entry));
  }
}
