import type { DetectedCueEntry } from '../types/api';

/**
 * Cue-gap histogram + the valley-based default for the chapter-selection slider.
 *
 * The slider maps to a silence-gap threshold logarithmically: slider 0 → maxGap
 * (fewest chapters), slider 1 → minGap (most). Cues with gap >= threshold become
 * chapters.
 */

// Slider ↔ gap-threshold mapping
function thresholdAt(s: number, minGap: number, maxGap: number): number {
  if (maxGap <= minGap) return minGap;
  return Math.exp(Math.log(maxGap) * (1 - s) + Math.log(minGap) * s);
}

// Inverse of thresholdAt
export function gapToSlider(gap: number, minGap: number, maxGap: number): number {
  if (maxGap <= minGap) return 0.5;
  const clamped = Math.max(minGap, Math.min(maxGap, gap));
  return Math.log(maxGap / clamped) / Math.log(maxGap / minGap);
}

// Snap to the slider's 0.01 step. ceil biases toward slightly more chapters.
export function quantizeSlider(raw: number): number {
  return Math.ceil(Math.min(1, Math.max(0, raw)) * 100) / 100;
}

// Bin gaps into numBars logarithmic buckets (bar 0 = longest gaps). Backs both
// the rendered bars and valley detection.
export function computeHistogram(cues: DetectedCueEntry[], minGap: number, maxGap: number, numBars: number): number[] {
  if (cues.length === 0 || maxGap <= minGap) return Array(numBars).fill(0) as number[];
  const counts: number[] = Array(numBars).fill(0);
  for (let i = 0; i < numBars; i++) {
    const gapLow = thresholdAt((i + 1) / numBars, minGap, maxGap);
    const gapHigh = thresholdAt(i / numBars, minGap, maxGap);
    counts[i] = cues.filter((c) => c.gap >= gapLow && c.gap < gapHigh).length;
  }
  return counts;
}

// ── Valley detection for the auto-selected default ──
// The histogram frequently surfaces a valley with a hill of long-gap "real chapters"
// on the left and hill of short-gap "false positives" on the right. We calculate the
// default slider position to fall just into valley's right slope for good measure.

// Moving-average width used to de-noise the histogram before peak detection.
const SMOOTH_WINDOW = 5;

// Skip detection below this many cues — too sparse to be reliable.
const MIN_CUES_FOR_VALLEY = 12;

// Ignore valley floors this close to either edge (taper, not a real gap).
const EDGE_MARGIN = 3;

// Min valley depth, as a fraction of its lower flanking peak.
const PROMINENCE_FRACTION = 0.35;

// Min smoothed peak height to bound a valley (ignores noise bumps).
const MIN_FLANK_PEAK = 2;

// How far up the right slope to land, as a fraction of the floor→peak rise.
// Scaled by valley crispness: a crisp valley's right slope is more likely
// to have false positives so it stays near the floor (MIN); a murky valley
// is more likely to have real chapters on the slope, so it climbs higher (MAX).
const RISE_FRACTION_MIN = 0.01;
const RISE_FRACTION_MAX = 0.8;

// Always advance at least this many bins past the floor.
const MIN_RIGHT_NUDGE = 1;

// Weight of reference count-match vs. valley prominence when scoring.
const REF_WEIGHT = 0.5;

// Centered moving average; the window shrinks at the array ends.
function centeredMovingAverage(values: number[], window: number): number[] {
  const radius = Math.floor(window / 2);
  const out: number[] = new Array(values.length);
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - radius); j <= Math.min(values.length - 1, i + radius); j++) {
      sum += values[j];
      n++;
    }
    out[i] = sum / n;
  }
  return out;
}

interface ValleyCandidate {
  floorBin: number;
  depth: number;
  chosenBin: number;
}

/**
 * Default slider value [0, 1] from the histogram valley, or null when there is
 * no clear valley (the caller then falls back). `refCueCounts` are existing
 * references' implied cue counts (chapters - 1), a secondary signal for ranking.
 */
export function findValleyDefault(hist: number[], refCueCounts: number[]): number | null {
  const total = hist.reduce((a, b) => a + b, 0);
  if (total < MIN_CUES_FOR_VALLEY) return null;

  const sm = centeredMovingAverage(hist, SMOOTH_WINDOW);
  const n = sm.length;

  // Local maxima (plateau ties keep the first bin).
  const allPeaks: number[] = [];
  for (let i = 0; i < n; i++) {
    const left = i > 0 ? sm[i - 1] : -Infinity;
    const right = i < n - 1 ? sm[i + 1] : -Infinity;
    if (sm[i] > left && sm[i] >= right) allPeaks.push(i);
  }

  // Drop small bumps so a stray cue can't split a wide valley in two.
  const peaks = allPeaks.filter((p) => sm[p] >= MIN_FLANK_PEAK);
  if (peaks.length < 2) return null;

  const candidates: ValleyCandidate[] = [];
  for (let k = 0; k < peaks.length - 1; k++) {
    const pL = peaks[k];
    const pR = peaks[k + 1];

    // Floor = lowest bin between the two flanking peaks.
    let floorBin = pL;
    for (let i = pL; i <= pR; i++) {
      if (sm[i] < sm[floorBin]) floorBin = i;
    }
    if (floorBin < EDGE_MARGIN || floorBin > n - 1 - EDGE_MARGIN) continue;

    // Require a real dip; the lower flank is what the valley must separate from.
    const floorVal = sm[floorBin];
    const flankPeak = Math.min(sm[pL], sm[pR]);
    const depth = flankPeak - floorVal;
    if (flankPeak < MIN_FLANK_PEAK || depth < PROMINENCE_FRACTION * flankPeak) continue;

    // Crisper valley (deeper vs. its flanks) → climb less; murkier → climb more.
    const crispness = Math.min(1, Math.max(0, (depth / flankPeak - PROMINENCE_FRACTION) / (1 - PROMINENCE_FRACTION)));
    const riseFraction = RISE_FRACTION_MAX - crispness * (RISE_FRACTION_MAX - RISE_FRACTION_MIN);

    // First bin (before the right peak) that reaches riseFraction up the slope.
    const riseTarget = floorVal + riseFraction * (sm[pR] - floorVal);
    let riseBin = floorBin;
    while (riseBin < pR && sm[riseBin] < riseTarget) riseBin++;
    const chosenBin = Math.min(Math.max(riseBin, floorBin + MIN_RIGHT_NUDGE), n);

    candidates.push({ floorBin, depth, chosenBin });
  }

  if (candidates.length === 0) return null;

  // Rank by prominence, blended with reference count-match when refs exist.
  const maxDepth = Math.max(...candidates.map((c) => c.depth));
  let best = candidates[0];
  let bestScore = -Infinity;
  for (const c of candidates) {
    const promNorm = maxDepth > 0 ? c.depth / maxDepth : 0;
    let score = promNorm;
    if (refCueCounts.length > 0) {
      // Cues this candidate selects = bars 0..chosenBin-1.
      let count = 0;
      for (let i = 0; i < c.chosenBin; i++) count += hist[i];
      // Log-space closeness to the nearest reference (+1 guards zeros).
      const countMatch = Math.max(...refCueCounts.map((r) => Math.exp(-Math.abs(Math.log((count + 1) / (r + 1))))));
      score = (1 - REF_WEIGHT) * promNorm + REF_WEIGHT * countMatch;
    }
    if (score > bestScore) {
      bestScore = score;
      best = c;
    }
  }

  return quantizeSlider(best.chosenBin / n);
}
