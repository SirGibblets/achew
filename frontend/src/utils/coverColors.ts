/**
 * Extract a small palette of vibrant, representative colors from a cover image.
 *
 * The cover is served same-origin (`/api/audiobookshelf/covers/...`), so reading
 * pixels back off a canvas does not taint it. If a cross-origin / tainted source
 * ever sneaks in, `getImageData` throws and we return an empty palette so the
 * caller can fall back to theme colors.
 */

interface Bucket {
  count: number;
  r: number;
  g: number;
  b: number;
}

/* Downscaled sample resolution — small enough to be cheap, large enough to be
   representative of the cover's color distribution. */
const SAMPLE_SIZE = 48;

/* Drop near-grayscale buckets: confetti built from muddy browns/grays reads as
   dirt, not celebration. Saturation is HSL-style chroma over (1 - |2L-1|). */
const MIN_SATURATION = 0.18;

/* Drop near-black and near-white so the confetti stays visible on both themes. */
const MIN_LIGHTNESS = 0.12;
const MAX_LIGHTNESS = 0.92;

/* Two picked colors closer than this (Euclidean RGB distance) are treated as the
   same hue, so the palette spreads across the cover instead of returning five
   shades of one blue. */
const MIN_COLOR_DISTANCE = 64;

function saturationAndLightness(r: number, g: number, b: number): { s: number; l: number } {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  return { s, l };
}

function toHex(r: number, g: number, b: number): string {
  const h = (n: number) => Math.round(n).toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

/**
 * Pull up to `max` vibrant colors from a fully-loaded image element.
 * Returns `[]` when the image is unusable (not loaded, tainted, or too dull).
 */
export function extractCoverColors(img: HTMLImageElement, max = 6): string[] {
  if (!img.complete || img.naturalWidth === 0) return [];

  const canvas = document.createElement('canvas');
  canvas.width = SAMPLE_SIZE;
  canvas.height = SAMPLE_SIZE;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return [];

  ctx.drawImage(img, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE);

  let data: Uint8ClampedArray;
  try {
    data = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE).data;
  } catch {
    // Tainted canvas (cross-origin without CORS) — let the caller fall back.
    return [];
  }

  // Quantize to 4 bits per channel so similar pixels share a bucket, then keep
  // the true averaged color of each bucket.
  const buckets = new Map<number, Bucket>();
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const a = data[i + 3];
    if (a < 125) continue;

    const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.count++;
      bucket.r += r;
      bucket.g += g;
      bucket.b += b;
    } else {
      buckets.set(key, { count: 1, r, g, b });
    }
  }

  // Average each bucket, keep only the vibrant ones, and score by a blend of how
  // common and how saturated the color is so dominant *and* punchy colors win.
  const candidates = [...buckets.values()]
    .map((bucket) => {
      const r = bucket.r / bucket.count;
      const g = bucket.g / bucket.count;
      const b = bucket.b / bucket.count;
      const { s, l } = saturationAndLightness(r, g, b);
      return { r, g, b, s, l, score: bucket.count * (0.35 + s) };
    })
    .filter((c) => c.s >= MIN_SATURATION && c.l >= MIN_LIGHTNESS && c.l <= MAX_LIGHTNESS)
    .sort((a, b) => b.score - a.score);

  const picked: { r: number; g: number; b: number }[] = [];
  for (const c of candidates) {
    if (picked.length >= max) break;
    const tooSimilar = picked.some((p) => {
      const dr = p.r - c.r;
      const dg = p.g - c.g;
      const db = p.b - c.b;
      return Math.sqrt(dr * dr + dg * dg + db * db) < MIN_COLOR_DISTANCE;
    });
    if (!tooSimilar) picked.push({ r: c.r, g: c.g, b: c.b });
  }

  return picked.map((c) => toHex(c.r, c.g, c.b));
}

/**
 * Resolve the cover image to a palette, waiting for it to load if necessary.
 * Always resolves (never rejects); yields `[]` when there's nothing usable.
 */
export function getCoverColors(img: HTMLImageElement | null | undefined): Promise<string[]> {
  if (!img) return Promise.resolve([]);
  if (img.complete) return Promise.resolve(extractCoverColors(img));

  return new Promise((resolve) => {
    const done = () => {
      img.removeEventListener('load', onLoad);
      img.removeEventListener('error', onError);
    };
    const onLoad = () => {
      done();
      resolve(extractCoverColors(img));
    };
    const onError = () => {
      done();
      resolve([]);
    };
    img.addEventListener('load', onLoad);
    img.addEventListener('error', onError);
  });
}

/* Theme-derived fallback palette, read live from the active theme's CSS custom
   properties so it tracks light/dark automatically. */
const THEME_COLOR_VARS = ['--primary', '--primary-contrast', '--accent-1', '--accent-2', '--success'];

export function getThemeColors(): string[] {
  const styles = getComputedStyle(document.documentElement);
  return THEME_COLOR_VARS.map((v) => styles.getPropertyValue(v).trim()).filter(Boolean);
}
