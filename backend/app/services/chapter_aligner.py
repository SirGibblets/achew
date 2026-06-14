"""Re-aligns a Chapter Reference's timestamps onto detected cues.

Uses a "skeleton fill" approach to chapter-cue alignment using **offset-invariant duration-shape
matching**, in three tiers:

1. SKELETON. Keep only the strongest ~N cues and align reference chapters to them by matching
   the *unadjusted reference durations* to the spacings between cues (a monotonic duration-shape
   DP). Matching relative spacing rather than absolute position makes it immune to a global
   front-matter offset and to per-chapter slop; prefiltering to strong cues removes the bulk of
   the decoy silences (e.g. the louder pause after a chapter title). The pool depth is
   coverage-aware (see SLACK): a narrow scan gets a shallower strong set, which measurably
   reduces decoy flips. The chapters that land are placed reliably and establish accurate LOCAL
   positions. This is the confident tier. The duration term needs a time-base scale; the global
   book/reference duration ratio is used first, then revised to the robust slope through the
   skeleton's own matches when the two disagree (see SCALE_REVISION_MIN_DELTA) — the ratio
   mis-scales when the duration difference sits in trailing/front content rather than spread
   across chapters, which would otherwise make the skeleton drift later with every chapter.

2. FILL. The skeleton leaves runs of chapters unmatched — weak-gap true boundaries that never
   made the strong set, and (crucially) true boundaries that sit off the global scale line behind
   a regional front-matter/step offset, which the skeleton's position prior penalises into being
   skipped. Recover each such run with a *second, local* duration-shape DP over the FULL cue set,
   bracketed by the confident skeleton positions around it. Anchoring on real bracket times
   absorbs the regional offset, and running the match locally lets duration-shape carry the chain
   across a step inside the hole — a single global pass cannot. Its duration term runs on a scale
   read off the bracketing skeleton anchors, not the global duration ratio: a long final chapter
   (or trailing content) skews the global ratio, which an unbracketed *tail* run would accumulate.
   Fills are flagged as guesses.

3. POLISH. The local DP fixes the SHAPE of a run but can leave it a couple of seconds off, parked
   on a parallel decoy chain that is equally spacing-consistent (a tie only position breaks). With
   every chapter now placed, re-snap each guess bracketed on BOTH sides to the cue nearest the
   position interpolated from its immediate placed neighbours, in a small window — fine enough to
   fix this drift, tight enough to leave genuinely step-shifted fills alone. An unbracketed tail is
   left to the fill (whose local scale already handles it), so polish never re-introduces drift.

Fills/polish only ever touch guesses; the confident skeleton tier is never moved, so the aligner
is never silently wrong on a recovered boundary. On the real fixtures (≤3min duration difference,
the design target) this scores ~97% of matchable chapters within 0.1s, the rest flagged rather
than confidently misplaced.

EXPANSION SIGNAL. Detection only covers the audio the pipeline extracted (± the extraction
padding around each reference timestamp), so a boundary that shifted beyond the padding —
typically offsetting insertions/removals that leave the total durations similar — is simply
invisible: no cue exists at it. When ``align`` is given the ``scanned_regions`` that detection
actually covered, it reports ``expansion_needed`` in the returned stats: True when some chapter
ended up placed on no cue at all AND part of the window the aligner would have searched for it
was never scanned. "We found nothing, but we never looked there" is not evidence the boundary
is missing, so the pipeline reacts by widening the extraction padding and re-running detection
and alignment once. A chapter whose searched window WAS fully scanned and still has no cue is a
genuinely missing boundary (e.g. two chapters narrated as one) — expansion cannot help it, so it
does not fire the signal by itself when its surroundings were densely covered. Known limit: a
shifted region whose every chapter gets captured by a decoy chain inside the scanned windows
leaves nothing unplaced and is undetectable post-hoc.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.api.routes.chapters import BasicChapter, DetectedCue
from app.core.constants import REALIGN_PADDING_EXPANDED

# Strong-cue set size = #chapters + SLACK, plus a quarter more on a WIDE scan only
# (max_drift >= REALIGN_PADDING_EXPANDED). The extra headroom exists to absorb strong
# NON-boundary silences (scene breaks, disc gaps) that a wide scan sweeps up alongside the
# true boundaries. A narrow scan never analyzed that audio — the cues the headroom was
# budgeted for don't exist in the pool — so the extra slots only admit mid-strength decoys
# near the boundaries, which measurably flips borderline skeleton matches on real books.
SLACK = 3

# Skeleton DP weights (duration-shape dominant, position a weak prior, gap a tie-breaker).
SK_W_POS = 0.25
SK_W_DUR = 1.0
SK_GAP_REWARD = 1.5
SK_UNMATCHED = 20.0

# Scale revision. The duration term scales reference spacings by the global duration ratio
# (book / reference). That ratio is wrong when the duration difference is NOT distributed
# across chapters but sits in trailing or front content — a long closing section, an interview
# after the last chapter, front matter: the chapter region then runs at ~1.0 while the ratio
# says otherwise, so the duration term over-/under-stretches and the skeleton drifts a little
# more with every chapter. After the first skeleton pass, re-estimate the scale as the robust
# (Theil–Sen) slope through the skeleton's own matches; if it disagrees with the ratio by more
# than MIN_DELTA, adopt it and re-run the skeleton once. The slope is offset-invariant and
# robust to a minority of decoy matches, and genuinely distributed drift (where the ratio is
# right) reproduces the ratio, so the revision is a no-op there.
SCALE_REVISION_MIN_DELTA = 0.003
# Sanity bounds: a realignment maps a book onto a near-equal-length reference, so a slope this
# far from 1.0 is a bad fit (mostly decoy matches), not a real time-base difference — ignore it.
SCALE_REVISION_BOUNDS = (0.9, 1.1)
# Don't trust a slope estimated from too few matches; fall back to the duration ratio.
SCALE_REVISION_MIN_MATCHES = 5

# Fill: a second, LOCAL duration-shape DP over each run of chapters the skeleton left
# unmatched, over the FULL cue set and bracketed by the confident skeleton positions around the
# run (a weak true boundary may not be in the strong set). It is purely duration-shape — position
# is only a hard search window, never a scoring term: the holes the skeleton leaves are exactly
# the regions sitting off the global scale line behind a front-matter/step offset, so any absolute
# -position cost would reintroduce the very bias that made the skeleton skip them. Duration-shape
# carries the chain across a step inside the hole; gap breaks ties toward the more boundary-like
# silence. A chapter with no acceptable local cue is left for _build to interpolate.
FILL_W_DUR = 1.0
FILL_GAP_REWARD = 1.0
FILL_UNMATCHED = 8.0
# The upper bracket can itself be a wrong skeleton match; weight its soft endpoint term low so a
# single bad anchor nudges but cannot poison an otherwise shape-consistent region.
FILL_W_END = 0.25
# A hole's duration term runs on a LOCAL scale read off the confident skeleton anchors around it,
# not the global duration ratio: a long final chapter (or trailing content) makes the global ratio
# a poor predictor of chapter spacings, which a tail fill would then accumulate. A two-sided hole
# uses its bracket-to-bracket slope; a tail uses the slope back across this many skeleton anchors.
FILL_TRAIL_ANCHORS = 3
# The entry term anchoring the chain to the lower bracket is capped (Huber-style): a step right at
# the bracket — e.g. a multi-disc "end of disc / start of disc" announcement that adds ~a minute to
# one chapter, where the disc-end silence is often the loudest cue in the book and gets matched as
# the boundary — must not rigidly drag the whole run to that wrong offset. Beyond the cap the entry
# term is flat, so the run instead locks onto the internally-consistent, stronger real chain. The
# cap sits above genuine chapter-length variation (a chapter running a few tens of seconds off its
# reference duration is honoured) and below a disc/section announcement, so only the latter is
# treated as an anchor we should stop trusting. A correct bracket's residual is tiny, so unaffected.
FILL_ENTRY_CAP = 50.0

# Polish: once every chapter is placed, the duration-shape DP can still leave a fill a couple of
# seconds off — sitting on a parallel decoy chain that is equally spacing-consistent, a tie only
# position breaks. Re-snap each guess to the cue nearest the position interpolated from its
# immediate placed neighbours, which now pin it locally. The window is deliberately small so it
# only corrects this fine parallel-chain drift and leaves a genuinely step-shifted fill (which
# sits far from the straddling interpolation) alone. Iterated so a corrected fill improves the
# next one's neighbour estimate.
POLISH_WINDOW = 6.0
POLISH_ITERS = 3


class ChapterAligner:
    def __init__(self, max_drift: float = 120.0, slack: int = SLACK):
        # The matching window floor — driven by the extraction padding upstream, so a genuinely
        # large drift (wide extraction window) is not re-narrowed.
        self.max_drift = max_drift
        self.slack = slack

    def align(
        self,
        ref_chapters: List[BasicChapter],
        detected_cues: List[DetectedCue],
        total_duration_ref: float,
        total_duration_actual: float,
        scanned_regions: Optional[List[Tuple[float, float]]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        n = len(ref_chapters)
        if n == 0:
            return [], {"scale": 1.0, "offset": 0.0, "expansion_needed": False}

        scale = total_duration_actual / total_duration_ref if total_duration_ref > 0 else 1.0
        ref = np.array([c.timestamp for c in ref_chapters], dtype=float)
        ref0 = ref[0]
        cue_t = np.array([c.timestamp for c in detected_cues], dtype=float)
        cue_g = np.array([c.gap for c in detected_cues], dtype=float)
        window = max(90.0, abs(total_duration_actual - total_duration_ref) * 2.0, self.max_drift)

        # placed[chapter] = (time, cue_index, residual, confident). Chapter 0 anchors at 0.
        placed: Dict[int, Tuple[float, int, float, bool]] = {0: (0.0, -1, 0.0, True)}

        if detected_cues:
            # ── Tier 1: skeleton on the strongest cues ──────────────────────
            # Pool depth is coverage-aware: the n//4 headroom only on a wide scan (see SLACK).
            headroom = n // 4 if self.max_drift >= REALIGN_PADDING_EXPANDED else 0
            n_keep = min(len(detected_cues), n + self.slack + headroom)
            strong = sorted(
                sorted(range(len(detected_cues)), key=lambda k: cue_g[k], reverse=True)[:n_keep],
                key=lambda k: cue_t[k],
            )
            s_time = cue_t[strong]
            s_gap = cue_g[strong]
            skel_match = self._skeleton_dp(ref, s_time, s_gap, scale, window)

            # Revise the scale if the slope through the skeleton's matches disagrees with the
            # global duration ratio (trailing/front content contaminating the ratio); re-run once.
            revised = self._scale_from_matches(ref, s_time, skel_match)
            if revised is not None and abs(revised - scale) > SCALE_REVISION_MIN_DELTA:
                scale = revised
                skel_match = self._skeleton_dp(ref, s_time, s_gap, scale, window)

            for i in range(1, n):
                j = skel_match[i]
                if j >= 0:
                    placed[i] = (float(s_time[j]), strong[j], 0.0, True)

            # ── Tier 2: fill each hole between skeleton anchors with a LOCAL duration-shape DP ──
            # The skeleton leaves runs of chapters unmatched — weak-gap boundaries, or true
            # boundaries that sit off the global scale line behind a front-matter/step offset. Re-run
            # the same offset-invariant duration-shape match locally over each such run, bracketed by
            # the confident skeleton positions around it (using the FULL cue set, since a weak true
            # boundary may not be in the strong set). Fills are flagged as guesses (is_guess=True):
            # the skeleton is the confident tier, a fill recovers a likely boundary without asserting
            # certainty.
            anchors = sorted(placed)
            for a in range(len(anchors)):
                lo = anchors[a]
                hi = anchors[a + 1] if a + 1 < len(anchors) else None
                interior = list(range(lo + 1, hi if hi is not None else n))
                if not interior:
                    continue
                t_lo = placed[lo][0]
                t_hi = placed[hi][0] if hi is not None else None
                r_scale = self._region_scale(a, anchors, placed, ref, scale)
                region = self._fill_region(interior, ref, cue_t, cue_g, r_scale, lo, t_lo, hi, t_hi, window)
                for i, (j, residual) in region.items():
                    placed[i] = (float(cue_t[j]), j, residual, False)

            # ── Tier 3: polish fills against their now-dense local neighbourhood ──
            self._polish(n, ref, cue_t, cue_g, placed)

        results = self._build(ref_chapters, placed, cue_g, scale)

        expansion_needed = scanned_regions is not None and self._needs_expansion(
            results, placed, window, scanned_regions, total_duration_actual
        )

        return results, {"scale": scale, "offset": -scale * ref0, "expansion_needed": expansion_needed}

    @staticmethod
    def _scale_from_matches(ref: np.ndarray, s_time: np.ndarray, skel_match: List[int]) -> Optional[float]:
        """Robust (Theil–Sen) slope of matched cue time vs reference time over the skeleton's
        confident matches — an offset-invariant estimate of the chapter region's time-base,
        immune to a minority of decoy matches. Returns None when too few matches to trust, or
        the slope is implausibly far from 1.0 (a bad fit rather than a real time-base shift)."""
        pts = [(ref[i], float(s_time[j])) for i, j in enumerate(skel_match) if j >= 0]
        if len(pts) < SCALE_REVISION_MIN_MATCHES:
            return None
        rs = np.array([p[0] for p in pts])
        cs = np.array([p[1] for p in pts])
        slopes = [
            (cs[b] - cs[a]) / (rs[b] - rs[a])
            for a in range(len(rs))
            for b in range(a + 1, len(rs))
            if rs[b] - rs[a] > 1e-6
        ]
        if not slopes:
            return None
        slope = float(np.median(slopes))
        lo, hi = SCALE_REVISION_BOUNDS
        return slope if lo < slope < hi else None

    @staticmethod
    def _needs_expansion(
        results: List[Dict[str, Any]],
        placed: Dict[int, Tuple[float, int, float, bool]],
        window: float,
        scanned_regions: List[Tuple[float, float]],
        total_duration_actual: float,
    ) -> bool:
        """Whether detection should be widened and alignment re-run: True when some chapter
        was placed on no cue at all (interpolated by ``_build``) and part of the ±``window``
        neighbourhood the aligner would have searched for it was never scanned. Finding no cue
        in audio we never analyzed is not evidence the boundary is missing — only a chapter
        whose searched window was fully covered is treated as genuinely cue-less."""
        regions = sorted(scanned_regions)

        def covered(lo: float, hi: float) -> bool:
            # Is [lo, hi] (clamped to the book) fully inside the union of scanned regions?
            lo, hi = max(0.0, lo), min(total_duration_actual, hi)
            if hi <= lo:
                return True  # nothing inside the book to scan
            pos = lo
            for s, e in regions:
                if s > pos:
                    return False
                pos = max(pos, e)
                if pos >= hi:
                    return True
            return pos >= hi

        for i in range(1, len(results)):
            if i in placed:
                continue  # placed chapters sit on detected cues, inside scanned audio
            t = float(results[i]["timestamp"])
            if not covered(t - window, t + window):
                return True
        return False

    def _skeleton_dp(
        self, ref: np.ndarray, s_time: np.ndarray, s_gap: np.ndarray, scale: float, window: float
    ) -> List[int]:
        """Monotonic DP matching reference chapters to strong cues, scored on duration-shape
        (spacing vs. reference spacing) plus a weak position prior and a gap tie-breaker.
        Chapters may be left unmatched and strong cues skipped; chapter 0 anchors at t=0."""
        n, m = len(ref), len(s_time)
        ref0 = ref[0]
        g_lo, g_hi = float(s_gap.min()), float(s_gap.max())
        g_span = g_hi - g_lo

        def unary(i: int, j: int) -> float:
            pos = abs(s_time[j] - scale * (ref[i] - ref0))
            rel = (s_gap[j] - g_lo) / g_span if g_span > 1e-6 else 0.5
            return SK_W_POS * pos - SK_GAP_REWARD * rel

        def dur(ip: int, i: int, tp: float, tc: float) -> float:
            return SK_W_DUR * abs((tc - tp) - scale * (ref[i] - ref[ip]))

        INF = float("inf")
        dp: List[Dict[int, float]] = [dict() for _ in range(n)]
        back: List[Dict[int, Optional[Tuple[int, int]]]] = [dict() for _ in range(n)]
        for i in range(1, n):
            for j in range(m):
                if abs(s_time[j] - scale * (ref[i] - ref0)) > window:
                    continue
                best, best_from = INF, None
                cost = unary(i, j) + (i - 1) * SK_UNMATCHED + dur(0, i, 0.0, s_time[j])
                if cost < best:
                    best, best_from = cost, (0, -1)
                for ip in range(1, i):
                    skipped = (i - ip - 1) * SK_UNMATCHED
                    for jp, prev in dp[ip].items():
                        if s_time[jp] >= s_time[j]:
                            continue
                        cost = prev + skipped + unary(i, j) + dur(ip, i, s_time[jp], s_time[j])
                        if cost < best:
                            best, best_from = cost, (ip, jp)
                if best < INF:
                    dp[i][j] = best
                    back[i][j] = best_from

        matches = [-1] * n
        best_end, end = (n - 1) * SK_UNMATCHED, None
        for ip in range(1, n):
            trailing = (n - 1 - ip) * SK_UNMATCHED
            for jp, cost in dp[ip].items():
                if cost + trailing < best_end:
                    best_end, end = cost + trailing, (ip, jp)
        state = end
        while state is not None:
            i, j = state
            if i == 0:
                break
            matches[i] = j
            state = back[i][j]
        return matches

    @staticmethod
    def _region_scale(
        a: int,
        anchors: List[int],
        placed: Dict[int, Tuple[float, int, float, bool]],
        ref: np.ndarray,
        scale: float,
    ) -> float:
        """Local time-per-reference-second for a TAIL hole (no upper bracket), read off the
        confident skeleton positions so it is immune to trailing-content contamination of the
        global ratio (a long final chapter throws the global ratio off, which an unbracketed tail
        would otherwise accumulate). A two-sided hole keeps the global ``scale`` — it is already
        bracketed, and its own brackets can be a wrong skeleton match whose slope would mislead.
        The tail uses the slope back across FILL_TRAIL_ANCHORS skeleton anchors."""
        lo = anchors[a]
        if a + 1 < len(anchors):
            return scale  # two-sided hole: bracketed, trust the global slope
        prev = anchors[max(0, a - FILL_TRAIL_ANCHORS)]
        return (placed[lo][0] - placed[prev][0]) / (ref[lo] - ref[prev]) if ref[lo] > ref[prev] else scale

    def _fill_region(
        self,
        interior: List[int],
        ref: np.ndarray,
        cue_t: np.ndarray,
        cue_g: np.ndarray,
        scale: float,
        lo: int,
        t_lo: float,
        hi: Optional[int],
        t_hi: Optional[float],
        window: float,
    ) -> Dict[int, Tuple[int, float]]:
        """Match a run of unmatched ``interior`` chapters to cues in the FULL set, bracketed by
        the confident skeleton anchors ``lo`` (at ``t_lo``) and, when present, ``hi`` (at
        ``t_hi``). Same monotonic duration-shape DP as the skeleton, but anchored on real bracket
        times so a regional offset is already absorbed. Returns ``{chapter: (cue_index, residual)}``
        for the chapters it places; chapters with no acceptable local cue are omitted."""
        # Candidate cues live strictly inside the bracket (after t_lo, before t_hi if bounded).
        if hi is not None and t_hi is not None:
            cand = np.where((cue_t > t_lo + 1e-6) & (cue_t < t_hi - 1e-6))[0]
        else:
            cand = np.where(cue_t > t_lo + 1e-6)[0]
        if len(cand) == 0:
            return {}
        c_t = cue_t[cand]
        c_g = cue_g[cand]
        g_lo, g_hi = float(c_g.min()), float(c_g.max())
        g_span = g_hi - g_lo

        def center(i: int) -> float:
            # Window center only (not a cost): local interpolation between bracket anchors,
            # extrapolated by scale for a tail. Bounds the search; never biases the score.
            if hi is not None and t_hi is not None and ref[hi] > ref[lo]:
                f = (ref[i] - ref[lo]) / (ref[hi] - ref[lo])
                return t_lo + f * (t_hi - t_lo)
            return t_lo + scale * (ref[i] - ref[lo])

        def unary(c: int) -> float:
            rel = (c_g[c] - g_lo) / g_span if g_span > 1e-6 else 0.5
            return -FILL_GAP_REWARD * rel

        def dur(ip: int, i: int, tp: float, tc: float) -> float:
            return FILL_W_DUR * abs((tc - tp) - scale * (ref[i] - ref[ip]))

        k_n, m = len(interior), len(cand)
        centers = [center(i) for i in interior]
        INF = float("inf")
        dp: List[Dict[int, float]] = [dict() for _ in range(k_n)]
        back: List[Dict[int, Optional[Tuple[int, int]]]] = [dict() for _ in range(k_n)]
        for k in range(k_n):
            i = interior[k]
            for c in range(m):
                if abs(c_t[c] - centers[k]) > window:
                    continue
                # Enter from the lower bracket anchor, skipping the k chapters before this one. The
                # entry term is capped so a step at the bracket cannot rigidly fix the run's offset.
                best = unary(c) + k * FILL_UNMATCHED + min(dur(lo, i, t_lo, c_t[c]), FILL_ENTRY_CAP)
                best_from: Optional[Tuple[int, int]] = (-1, -1)
                for kp in range(k):
                    skipped = (k - kp - 1) * FILL_UNMATCHED
                    for cp, prev in dp[kp].items():
                        if c_t[cp] >= c_t[c]:
                            continue
                        cost = prev + skipped + unary(c) + dur(interior[kp], i, c_t[cp], c_t[c])
                        if cost < best:
                            best, best_from = cost, (kp, cp)
                dp[k][c] = best
                back[k][c] = best_from

        # Terminate at any matched chapter; when the run is bounded above, a soft duration term to
        # the upper anchor keeps the last match on the right spacing.
        best_end, end = INF, None
        for kp in range(k_n):
            trailing = (k_n - 1 - kp) * FILL_UNMATCHED
            for cp, cost in dp[kp].items():
                total = cost + trailing
                if hi is not None and t_hi is not None:
                    total += FILL_W_END * dur(interior[kp], hi, c_t[cp], t_hi)
                if total < best_end:
                    best_end, end = total, (kp, cp)

        matches: Dict[int, Tuple[int, float]] = {}
        state = end
        while state is not None:
            kp, cp = state
            if kp < 0:
                break
            matches[interior[kp]] = (int(cand[cp]), float(abs(c_t[cp] - centers[kp])))
            state = back[kp][cp]
        return matches

    @staticmethod
    def _polish(
        n: int,
        ref: np.ndarray,
        cue_t: np.ndarray,
        cue_g: np.ndarray,
        placed: Dict[int, Tuple[float, int, float, bool]],
    ) -> None:
        """Re-snap each guess (fill) to the cue nearest the position interpolated from its immediate
        placed neighbours, within POLISH_WINDOW. Only chapters bracketed on BOTH sides are polished:
        an unbracketed tail would have to extrapolate, which is exactly the drift the fill's local
        scale already handles — re-introducing it here, and propagating it backward through the
        interpolation chain, is what we must avoid. Confident skeleton placements are never moved,
        and the window stays inside the bracketing neighbours so monotonicity holds. In-place."""
        for _ in range(POLISH_ITERS):
            changed = False
            for i in range(1, n):
                entry = placed.get(i)
                if entry is None or entry[3]:  # skip unplaced and confident (skeleton) chapters
                    continue
                lo = max((k for k in placed if k < i), default=None)
                hi = min((k for k in placed if k > i), default=None)
                if lo is None or hi is None or ref[hi] <= ref[lo]:
                    continue
                lo_t, hi_t = placed[lo][0], placed[hi][0]
                f = (ref[i] - ref[lo]) / (ref[hi] - ref[lo])
                pred = lo_t + f * (hi_t - lo_t)
                within = np.where((cue_t > lo_t) & (cue_t < hi_t) & (np.abs(cue_t - pred) <= POLISH_WINDOW))[0]
                if len(within) == 0:
                    continue
                dist = np.abs(cue_t[within] - pred)
                nearest = float(dist.min())
                # Among cues within ~0.5 s of the nearest, prefer the stronger (boundary-like) gap.
                close = within[dist <= nearest + 0.5]
                j = int(close[np.argmax(cue_g[close])])
                if j != entry[1]:
                    placed[i] = (float(cue_t[j]), j, float(abs(cue_t[j] - pred)), False)
                    changed = True
            if not changed:
                break

    def _build(
        self,
        ref_chapters: List[BasicChapter],
        placed: Dict[int, Tuple[float, int, float, bool]],
        cue_g: np.ndarray,
        scale: float,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i, chapter in enumerate(ref_chapters):
            if i == 0:
                results.append(self._result(chapter.title, 0.0, 1.0, False, 0.0))
                continue
            if i in placed:
                t, idx, _res, confident = placed[i]
                silence = float(cue_g[idx]) if idx >= 0 else 0.0
                results.append(self._result(chapter.title, t, 0.85 if confident else 0.35, not confident, silence))
            else:
                lo = max((k for k in placed if k < i), default=0)
                hi = min((k for k in placed if k > i), default=None)
                lo_ref = ref_chapters[lo].timestamp
                lo_t = placed[lo][0]
                if hi is not None and ref_chapters[hi].timestamp > lo_ref:
                    f = (ref_chapters[i].timestamp - lo_ref) / (ref_chapters[hi].timestamp - lo_ref)
                    ts = lo_t + f * (placed[hi][0] - lo_t)
                else:
                    ts = lo_t + scale * (ref_chapters[i].timestamp - lo_ref)
                results.append(self._result(chapter.title, max(0.0, ts), 0.25, True, 0.0))
        return results

    @staticmethod
    def _result(title: str, timestamp: float, confidence: float, is_guess: bool, silence: float) -> Dict[str, Any]:
        return {
            "title": title,
            "timestamp": timestamp,
            "confidence": confidence,
            "is_guess": is_guess,
            "matched_silence": silence,
        }
