import numpy as np
from sklearn.linear_model import RANSACRegressor


class ChapterAligner:
    def __init__(self, time_weight=1.0, silence_weight=10.0, skip_penalty=20.0, ransac_threshold=30.0):
        """
        :param time_weight: Penalty multiplier for time difference.
        :param silence_weight: Reward multiplier for silence duration.
        :param skip_penalty: Cost to skip a chapter (leave it as a guess).
        :param ransac_threshold: (Seconds) How far a point can be from the line to be considered an "inlier".
        """
        self.w_time = time_weight
        self.w_silence = silence_weight
        self.skip_penalty = skip_penalty
        self.ransac_threshold = ransac_threshold

    def align(self, source_chapters, detected_cues, total_duration_source, total_duration_actual):
        src_times = np.array([c["time"] for c in source_chapters])
        cue_times = np.array([c["time"] for c in detected_cues])

        # --- Initial drift correction ---

        X_candidates = []
        y_candidates = []

        for t_expected in src_times:
            idx = (np.abs(cue_times - t_expected)).argmin()
            t_nearest = cue_times[idx]

            if abs(t_nearest - t_expected) < 600:
                X_candidates.append(t_expected)
                y_candidates.append(t_nearest)

        scale = total_duration_actual / total_duration_source if total_duration_source > 0 else 1.0
        offset = 0.0

        if len(X_candidates) >= 2:
            X = np.array(X_candidates).reshape(-1, 1)
            y = np.array(y_candidates)

            try:
                reg = RANSACRegressor(min_samples=2, residual_threshold=self.ransac_threshold, random_state=42)
                reg.fit(X, y)

                scale = reg.estimator_.coef_[0]
                offset = reg.estimator_.intercept_

                if not (0.8 <= scale <= 1.2):
                    scale = total_duration_actual / total_duration_source
                    offset = 0.0
            except Exception:
                pass

        corrected_times = (src_times * scale) + offset

        # --- Establish cost matrix ---

        n_chapters = len(source_chapters)
        n_cues = len(detected_cues)

        dp = np.full((n_chapters + 1, n_cues + 1), np.inf)
        dp[0, 0] = 0

        traceback = np.zeros((n_chapters + 1, n_cues + 1), dtype=int)

        for i in range(1, n_chapters + 1):
            dp[i, 0] = dp[i - 1, 0] + self.skip_penalty
            traceback[i, 0] = 1
        for j in range(1, n_cues + 1):
            dp[0, j] = dp[0, j - 1] + 0
            traceback[0, j] = 2

        for i in range(1, n_chapters + 1):
            for j in range(1, n_cues + 1):
                t_expected = corrected_times[i - 1]
                t_actual = detected_cues[j - 1]["time"]

                time_diff = abs(t_expected - t_actual)
                time_cost = time_diff * self.w_time

                silence_val = detected_cues[j - 1]["silence_duration"]
                silence_reward = np.log(silence_val + 1) * self.w_silence

                match_cost = time_cost - silence_reward

                score_match = dp[i - 1, j - 1] + match_cost
                score_skip_chapter = dp[i - 1, j] + self.skip_penalty
                score_skip_cue = dp[i, j - 1] + 0

                best_score = min(score_match, score_skip_chapter, score_skip_cue)
                dp[i, j] = best_score

                if best_score == score_match:
                    traceback[i, j] = 0
                elif best_score == score_skip_chapter:
                    traceback[i, j] = 1
                else:
                    traceback[i, j] = 2

        # --- Find cheapest path ---

        aligned_chapters = []
        i, j = n_chapters, n_cues
        results_reversed = []

        while i > 0 or j > 0:
            if i > 0 and j > 0 and traceback[i, j] == 0:
                cue = detected_cues[j - 1]
                rec = {
                    "title": source_chapters[i - 1]["title"],
                    "timestamp": cue["time"],
                    "confidence": self._calculate_confidence(corrected_times[i - 1], cue),
                    "is_guess": False,
                    "matched_silence": cue["silence_duration"],
                }
                results_reversed.append(rec)
                i -= 1
                j -= 1
            elif i > 0 and (j == 0 or traceback[i, j] == 1):
                rec = {
                    "title": source_chapters[i - 1]["title"],
                    "timestamp": None,
                    "confidence": 0.0,
                    "is_guess": True,
                    "matched_silence": 0,
                }
                results_reversed.append(rec)
                i -= 1
            else:
                j -= 1

        aligned_chapters = results_reversed[::-1]

        # --- Fill in guesses ---

        for idx, item in enumerate(aligned_chapters):
            if item["timestamp"] is None:
                original_time = source_chapters[idx]["time"]
                predicted_time = (original_time * scale) + offset
                item["timestamp"] = max(0.0, predicted_time)

        return aligned_chapters, {"scale": scale, "offset": offset}

    def _calculate_confidence(self, expected_time, cue):
        time_diff = abs(expected_time - cue["time"])
        silence = cue["silence_duration"]

        time_score = max(0, 1 - (time_diff / 60.0))
        silence_score = min(1.0, silence / 4.0)

        return (0.6 * time_score) + (0.4 * silence_score)
