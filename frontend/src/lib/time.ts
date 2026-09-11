const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Formats a unix-seconds timestamp as a short, human-friendly relative label
 * (e.g. "just now", "2m ago", "3h ago", "yesterday", "5d ago").
 *
 * `now` defaults to the current time but can be passed explicitly for
 * deterministic tests.
 */
export function relativeTime(unixSeconds: number, now: number = Date.now() / 1000): string {
  const diff = Math.max(0, now - unixSeconds);
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < 2 * DAY) return "yesterday";
  return `${Math.floor(diff / DAY)}d ago`;
}

/**
 * Formats a duration in seconds (e.g. a process uptime) as a compact label
 * like "45s", "12m", "3h 5m", or "2d 4h" — the coarsest two units needed.
 */
export function formatUptime(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / DAY);
  const hours = Math.floor((seconds % DAY) / HOUR);
  const minutes = Math.floor((seconds % HOUR) / MINUTE);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${seconds}s`;
}
