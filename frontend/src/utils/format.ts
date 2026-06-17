/**
 * Format a duration in seconds as a compact `Xh Ym` / `Ym` string.
 *
 * Pass `includeSeconds` to append `Zs` — useful where second-level precision
 * matters, e.g. comparing a chapter reference's duration against the book's.
 *
 * Leading and trailing zero-value units are dropped (`12h 0m 0s` → `12h`,
 * `5m 0s` → `5m`, `1m 12s`, `30s`), but interior zeros are kept so the most
 * significant unit stays anchored (`1h 0m 5s`).
 */
export function formatDuration(seconds: number | null | undefined, includeSeconds = false): string {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  const units: { value: number; suffix: string }[] = [
    { value: hours, suffix: 'h' },
    { value: minutes, suffix: 'm' },
  ];
  if (includeSeconds) units.push({ value: secs, suffix: 's' });

  let start = 0;
  let end = units.length - 1;
  while (start < end && units[start].value === 0) start++;
  while (end > start && units[end].value === 0) end--;

  return units
    .slice(start, end + 1)
    .map((u) => `${u.value}${u.suffix}`)
    .join(' ');
}

/** Format a byte count as a human-readable size (one decimal, binary units). */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  // No decimal for plain bytes; one decimal for larger units.
  const formatted = exponent === 0 ? String(value) : value.toFixed(1);
  return `${formatted} ${units[exponent]}`;
}

/** Condense a list of names to a single-line label. */
export function formatNameList(names: string[]): { display: string; full: string; count: number } {
  const cleaned = names.map((n) => n.trim()).filter(Boolean);
  const full = cleaned.join(', ');
  if (cleaned.length <= 2) {
    return { display: full, full, count: cleaned.length };
  }
  return { display: `${cleaned[0]} +${cleaned.length - 1} others`, full, count: cleaned.length };
}
