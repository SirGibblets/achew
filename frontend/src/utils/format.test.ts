import { describe, expect, it } from 'vitest';
import { formatTimeAgo } from './format';

const NOW = Date.UTC(2026, 9, 25, 12);
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe('formatTimeAgo', () => {
  it('collapses the last minute and future timestamps to "just now"', () => {
    expect(formatTimeAgo(NOW - 30_000, NOW)).toBe('just now');
    expect(formatTimeAgo(NOW + 5 * MINUTE, NOW)).toBe('just now');
  });

  it('counts minutes, then hours, within the first day', () => {
    expect(formatTimeAgo(NOW - 5 * MINUTE, NOW)).toBe('5m ago');
    expect(formatTimeAgo(NOW - 59 * MINUTE, NOW)).toBe('59m ago');
    expect(formatTimeAgo(NOW - HOUR, NOW)).toBe('1h ago');
    expect(formatTimeAgo(NOW - 23 * HOUR, NOW)).toBe('23h ago');
  });

  it('names a one-day gap, then counts days and weeks', () => {
    expect(formatTimeAgo(NOW - DAY, NOW)).toBe('yesterday');
    expect(formatTimeAgo(NOW - 4 * DAY, NOW)).toBe('4d ago');
    expect(formatTimeAgo(NOW - 13 * DAY, NOW)).toBe('13d ago');
    expect(formatTimeAgo(NOW - 14 * DAY, NOW)).toBe('2w ago');
  });
});
