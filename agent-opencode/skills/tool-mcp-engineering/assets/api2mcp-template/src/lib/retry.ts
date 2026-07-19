const RETRYABLE = new Set([429, 500, 502, 503, 504]);

export async function retry<T>(fn: () => Promise<T>, attempts = 3): Promise<T> {
  let last: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await fn();
    } catch (err) {
      last = err;
      // Only retry on transient/network errors, not client errors (4xx except 429).
      const status = (err as Error & { status?: number }).status;
      if (status !== undefined && !RETRYABLE.has(status)) throw err;
      if (i === attempts - 1) break;
      await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** i + Math.random() * 100));
    }
  }
  throw last instanceof Error ? last : new Error(String(last));
}
