import { useState, useCallback } from 'react';

/**
 * Reusable hook to execute an asynchronous API function and track
 * loading, success data, and error state in a consistent structure.
 *
 * @param {Function} apiFunc - Async function returning a promise
 * @returns {{
 *   data: any,
 *   error: string | null,
 *   loading: boolean,
 *   execute: (...args: any[]) => Promise<any>,
 *   reset: () => void
 * }}
 */
export function useApi(apiFunc) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);
      try {
        const result = await apiFunc(...args);
        setData(result);
        return result;
      } catch (err) {
        const message = err?.message || 'An unexpected error occurred';
        setError(message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [apiFunc]
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, execute, reset };
}

export default useApi;
