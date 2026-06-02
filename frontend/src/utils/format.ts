/** Format a duration in seconds as a compact `Xh Ym` / `Ym` string. */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
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
