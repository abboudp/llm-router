/**
 * Builds `path?a=1&b=2` from a base path and a params object, skipping any
 * key whose value is `undefined` or an empty string. Values are URL-encoded
 * via `URLSearchParams`.
 */
export function withQuery(
  path: string,
  params: Record<string, string | number | undefined>,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}
