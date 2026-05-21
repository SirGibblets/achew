import { SvelteMap } from 'svelte/reactivity';

/**
 * Maximum gap, in seconds, between a target timestamp and a reference cue's timestamp
 * for the two to be considered "aligned".
 */
export const ALIGNMENT_TOLERANCE_SECONDS = 5;

export interface AlignedPair<T> {
  refChapterIndex: number;
  refTitle: string;
  target: T;
  dist: number;
}

/**
 * For each reference chapter, find the closest target within `tolerance` seconds and pair them up.
 *
 * Deduplicates by target: if two reference chapters match the same target, the closer one wins.
 * Returns a reactive map keyed by `target.id`. The pair includes `refChapterIndex`, the
 * index of the reference chapter that produced it — useful for identifying which reference chapters
 * went unaligned.
 */
export function alignByTimestamp<T extends { id: string; timestamp: number }>(
  targets: T[],
  refChapters: { timestamp: number; title: string }[],
  tolerance: number = ALIGNMENT_TOLERANCE_SECONDS,
): SvelteMap<string, AlignedPair<T>> {
  const map = new SvelteMap<string, AlignedPair<T>>();
  if (!refChapters.length || !targets.length) return map;

  for (let i = 0; i < refChapters.length; i++) {
    const refChapter = refChapters[i];
    let best: T | null = null;
    let bestDist = Infinity;
    for (const target of targets) {
      const d = Math.abs(refChapter.timestamp - target.timestamp);
      if (d <= tolerance && d < bestDist) {
        bestDist = d;
        best = target;
      }
    }
    if (!best) continue;

    const existing = map.get(best.id);
    if (!existing || bestDist < existing.dist) {
      map.set(best.id, {
        refChapterIndex: i,
        refTitle: refChapter.title,
        target: best,
        dist: bestDist,
      });
    }
  }
  return map;
}
