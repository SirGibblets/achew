import { SvelteMap } from 'svelte/reactivity';

/**
 * Maximum gap, in seconds, between a target timestamp and a source cue's timestamp
 * for the two to be considered "aligned".
 */
export const ALIGNMENT_TOLERANCE_SECONDS = 5;

export interface AlignedPair<T> {
  sourceChapterIndex: number;
  sourceTitle: string;
  target: T;
  dist: number;
}

/**
 * For each source chapter, find the closest target within `tolerance` seconds and pair them up.
 *
 * Deduplicates by target: if two source chapters match the same target, the closer one wins.
 * Returns a reactive map keyed by `target.id`. The pair includes `sourceChapterIndex`, the
 * index of the source chapter that produced it — useful for identifying which source chapters
 * went unaligned.
 */
export function alignByTimestamp<T extends { id: string; timestamp: number }>(
  targets: T[],
  sourceChapters: { timestamp: number; title: string }[],
  tolerance: number = ALIGNMENT_TOLERANCE_SECONDS,
): SvelteMap<string, AlignedPair<T>> {
  const map = new SvelteMap<string, AlignedPair<T>>();
  if (!sourceChapters.length || !targets.length) return map;

  for (let i = 0; i < sourceChapters.length; i++) {
    const sourceChapter = sourceChapters[i];
    let best: T | null = null;
    let bestDist = Infinity;
    for (const target of targets) {
      const d = Math.abs(sourceChapter.timestamp - target.timestamp);
      if (d <= tolerance && d < bestDist) {
        bestDist = d;
        best = target;
      }
    }
    if (!best) continue;

    const existing = map.get(best.id);
    if (!existing || bestDist < existing.dist) {
      map.set(best.id, {
        sourceChapterIndex: i,
        sourceTitle: sourceChapter.title,
        target: best,
        dist: bestDist,
      });
    }
  }
  return map;
}
