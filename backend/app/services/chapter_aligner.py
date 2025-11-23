import numpy as np
from typing import List, Dict, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class ChapterAligner:
    def __init__(self, ransac_threshold=30.0, max_drift=120.0):
        self.ransac_threshold = ransac_threshold
        self.max_drift = max_drift

    def align(
        self, 
        source_chapters: List[Dict[str, Any]], 
        detected_cues: List[Dict[str, Any]], 
        total_duration_source: float, 
        total_duration_actual: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        if not source_chapters:
            return [], {"scale": 1.0, "offset": 0.0}
            
        if not detected_cues:
            return self._fallback_alignment(source_chapters, total_duration_source, total_duration_actual)
        
        src_times = np.array([c["time"] for c in source_chapters])
        cue_times = np.array([c["time"] for c in detected_cues])
        cue_silences = np.array([c["silence_duration"] for c in detected_cues])
        
        scale, offset = self._estimate_transform(
            src_times, cue_times, cue_silences,
            total_duration_source, total_duration_actual
        )
        
        expected_times = src_times * scale + offset
        
        matches = self._match_chapters_to_cues(
            expected_times, cue_times, cue_silences
        )
        
        aligned_chapters = self._build_results(
            source_chapters, detected_cues, matches, expected_times, scale, offset
        )
        
        return aligned_chapters, {"scale": scale, "offset": offset}
    
    def _estimate_transform(
        self,
        src_times: np.ndarray,
        cue_times: np.ndarray,
        cue_silences: np.ndarray,
        total_duration_source: float,
        total_duration_actual: float
    ) -> Tuple[float, float]:
        n_src = len(src_times)
        n_cues = len(cue_times)
        
        base_scale = total_duration_actual / total_duration_source if total_duration_source > 0 else 1.0
        base_offset = 0.0
        
        candidates_x = []
        candidates_y = []
        weights = []
        
        for src_t in src_times:
            expected_t = src_t * base_scale + base_offset
            
            time_diffs = np.abs(cue_times - expected_t)
            within_window = time_diffs < 120.0
            
            if not np.any(within_window):
                continue
            
            nearby_indices = np.where(within_window)[0]
            nearby_times = cue_times[nearby_indices]
            nearby_silences = cue_silences[nearby_indices]
            nearby_diffs = time_diffs[nearby_indices]
            
            silence_scores = np.minimum(nearby_silences / 3.0, 1.0)
            time_scores = np.maximum(0, 1 - nearby_diffs / 60.0)
            combined_scores = silence_scores * 0.6 + time_scores * 0.4
            
            best_idx = nearby_indices[np.argmax(combined_scores)]
            best_cue_t = cue_times[best_idx]
            
            candidates_x.append(src_t)
            candidates_y.append(best_cue_t)
            weights.append(combined_scores[np.argmax(combined_scores)])
        
        if len(candidates_x) < 2:
            logger.warning(f"Insufficient anchor points ({len(candidates_x)}) for transform estimation, using duration ratio")
            return base_scale, base_offset
        
        X = np.array(candidates_x)
        y = np.array(candidates_y)
        w = np.array(weights)
        
        W = np.diag(w)
        X_mat = np.column_stack([X, np.ones(len(X))])
        
        try:
            XtWX = X_mat.T @ W @ X_mat
            XtWy = X_mat.T @ W @ y
            params = np.linalg.solve(XtWX, XtWy)
            scale, offset = params[0], params[1]
            
            if not (0.90 <= scale <= 1.10):
                logger.warning(f"Estimated scale {scale:.3f} outside reasonable range, using duration ratio")
                scale = base_scale
                offset = base_offset
            
            if abs(offset) > 300:
                logger.warning(f"Estimated offset {offset:.1f}s seems too large, resetting to 0")
                offset = 0.0
                
        except np.linalg.LinAlgError:
            logger.warning("Linear regression failed, using duration ratio")
            scale = base_scale
            offset = base_offset
        
        logger.info(f"Transform estimation: scale={scale:.4f}, offset={offset:.2f}s using {len(candidates_x)} anchor points")
        return scale, offset
    
    def _match_chapters_to_cues(
        self,
        expected_times: np.ndarray,
        cue_times: np.ndarray,
        cue_silences: np.ndarray
    ) -> List[int]:
        n_chapters = len(expected_times)
        n_cues = len(cue_times)
        
        INF = float('inf')
        dp = [[INF] * (n_cues + 1) for _ in range(n_chapters + 1)]
        
        traceback = [[None] * (n_cues + 1) for _ in range(n_chapters + 1)]
        
        dp[0][0] = 0.0
        traceback[0][0] = (0, 0, -1)
        
        for j in range(1, n_cues + 1):
            dp[0][j] = 0.0
            traceback[0][j] = (0, j - 1, -1)
        
        for i in range(1, n_chapters + 1):
            expected_t = expected_times[i - 1]
            
            for j in range(i, n_cues + 1):
                cue_t = cue_times[j - 1]
                silence = cue_silences[j - 1]
                
                match_cost = self._calculate_match_cost(expected_t, cue_t, silence)
                
                if dp[i - 1][j - 1] + match_cost < dp[i][j]:
                    dp[i][j] = dp[i - 1][j - 1] + match_cost
                    traceback[i][j] = (i - 1, j - 1, j - 1)
                
                skip_cost = 0.0
                
                if j > 0 and dp[i][j - 1] + skip_cost < dp[i][j]:
                    dp[i][j] = dp[i][j - 1] + skip_cost
                    traceback[i][j] = traceback[i][j - 1]
                
                no_match_cost = 50.0
                
                if j > 0 and dp[i - 1][j] + no_match_cost < dp[i][j]:
                    dp[i][j] = dp[i - 1][j] + no_match_cost
                    traceback[i][j] = (i - 1, j, -1)
        
        matches = [-1] * n_chapters
        
        best_j = n_cues
        best_cost = dp[n_chapters][best_j]
        
        i, j = n_chapters, best_j
        while i > 0:
            if traceback[i][j] is None:
                break
            prev_i, prev_j, matched_cue = traceback[i][j]
            
            if prev_i == i - 1 and matched_cue >= 0:
                matches[i - 1] = matched_cue
            
            i, j = prev_i, prev_j
        
        return matches
    
    def _calculate_match_cost(self, expected_t: float, cue_t: float, silence: float) -> float:
        time_diff = abs(expected_t - cue_t)
        
        time_penalty = (time_diff / 2.0) ** 1.5
        
        silence_reward = min(silence * 7.5, 25.0)
        
        cost = time_penalty - silence_reward
        
        if time_diff > self.max_drift:
            cost += 1000.0
        
        return cost
    
    def _build_results(
        self,
        source_chapters: List[Dict[str, Any]],
        detected_cues: List[Dict[str, Any]],
        matches: List[int],
        expected_times: np.ndarray,
        scale: float,
        offset: float
    ) -> List[Dict[str, Any]]:
        results = []
        
        for i, src_chapter in enumerate(source_chapters):
            match_idx = matches[i]
            
            if match_idx >= 0:
                cue = detected_cues[match_idx]
                timestamp = cue["time"]
                silence = cue["silence_duration"]
                
                time_diff = abs(expected_times[i] - timestamp)
                confidence = self._calculate_confidence(time_diff, silence)
                
                results.append({
                    "title": src_chapter["title"],
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "is_guess": False,
                    "matched_silence": silence,
                })
            else:
                timestamp = max(0.0, expected_times[i])
                
                results.append({
                    "title": src_chapter["title"],
                    "timestamp": timestamp,
                    "confidence": 0.3,
                    "is_guess": True,
                    "matched_silence": 0.0,
                })
        
        return results
    
    def _calculate_confidence(self, time_diff: float, silence: float) -> float:
        time_score = np.exp(-time_diff / 30.0)
        
        silence_score = min(silence / 4.0, 1.0)
        
        confidence = 0.65 * time_score + 0.35 * silence_score
        
        return float(np.clip(confidence, 0.0, 1.0))
    
    def _fallback_alignment(
        self,
        source_chapters: List[Dict[str, Any]],
        total_duration_source: float,
        total_duration_actual: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        scale = total_duration_actual / total_duration_source if total_duration_source > 0 else 1.0
        offset = 0.0
        
        results = []
        for chapter in source_chapters:
            timestamp = max(0.0, chapter["time"] * scale + offset)
            results.append({
                "title": chapter["title"],
                "timestamp": timestamp,
                "confidence": 0.2,
                "is_guess": True,
                "matched_silence": 0.0,
            })
        
        return results, {"scale": scale, "offset": offset}
