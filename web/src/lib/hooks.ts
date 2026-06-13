import { useCallback, useEffect, useState } from "react";

// Tiny async-data hook: tracks loading/error/data and exposes a refetch.
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fn()
      .then(setData)
      .catch((e) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(run, [run]);
  return { data, loading, error, refetch: run };
}

export const pct = (x?: number | null) =>
  x == null ? "—" : `${Math.round(x * 100)}%`;
