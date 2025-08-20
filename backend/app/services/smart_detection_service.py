import logging
from typing import List, Tuple, Dict

import numpy as np
from sklearn.cluster import KMeans

from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


class SmartDetectionService:
    """Service for detecting chapter boundaries using audio analysis and k-means clustering"""

    def __init__(self, progress_callback: ProgressCallback, smart_detect_config=None):
        self.progress_callback: ProgressCallback = progress_callback

        # Use smart detect config if provided, otherwise use defaults
        if smart_detect_config:
            self.asr_buffer = smart_detect_config.asr_buffer
            self.segment_length = smart_detect_config.segment_length
            self.min_clip_length = smart_detect_config.min_clip_length
        else:
            # Default values (same as before)
            self.asr_buffer = 0.25
            self.segment_length = 8.0
            self.min_clip_length = 1.0

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: dict = None):
        """Notify progress via callback"""
        self.progress_callback(step, percent, message, details or {})

    def generate_cue_set(
        self,
        silences: List[Tuple[float, float]],
        book_length: float,
        k_clusters: int,
    ) -> Dict[int, List[float]]:
        """Generate cue set options using k-means clustering on silence durations"""

        if not silences or k_clusters < 2:
            return {}

        # Prepare data for clustering
        silence_durations = np.array([[s[1] - s[0]] for s in silences])

        # Perform k-means clustering
        try:
            kmeans = KMeans(n_clusters=k_clusters, random_state=1337, n_init=10).fit(silence_durations)
        except Exception as e:
            logger.error(f"K-means clustering failed: {e}")
            return {}

        cue_sets: Dict[int, List[float]] = {}

        for i in range(k_clusters - 1):
            top_n = i + 1

            cue_set = []

            # Identify the clusters with the longest silences
            cluster_centers = kmeans.cluster_centers_
            cluster_ranks = np.argsort(-cluster_centers.flatten())[:top_n]

            # Select silences from the clusters with longer durations
            for idx, silence in enumerate(silences):
                if kmeans.labels_[idx] in cluster_ranks:
                    new_cue = silence[1] - self.asr_buffer

                    # Ensure the new cue is not too close to existing cues
                    if any(abs(new_cue - existing_cue) < self.min_clip_length for existing_cue in cue_set):
                        continue

                    cue_set.append(new_cue)

            # Sort chapter silences
            cue_set.sort()

            # If the first element is less than our segment length, change it to 0
            if cue_set and cue_set[0] <= (self.segment_length + self.min_clip_length):
                cue_set[0] = 0
            else:
                cue_set.insert(0, 0)

            # If the last element is greater than the book length minus segment length, remove it
            if cue_set and cue_set[-1] > (book_length - self.segment_length):
                cue_set.pop()

            cue_sets[len(cue_set)] = cue_set

        return cue_sets

    @staticmethod
    def _filter_consecutive_counts(chapter_counts: List[int]) -> List[int]:
        """Filter out consecutive counts to reduce cue set options.

        For groups of sequential counts:
        - If group has only 2 options: keep the higher option
        - If group has 3+ options: keep first and last option in the group
        """
        if len(chapter_counts) <= 1:
            return chapter_counts

        filtered_counts = []
        i = 0

        while i < len(chapter_counts):
            # Start of a potential consecutive group
            group_start = i

            # Find the end of the consecutive group
            while i + 1 < len(chapter_counts) and chapter_counts[i + 1] == chapter_counts[i] + 1:
                i += 1

            group_end = i
            group_size = group_end - group_start + 1

            if group_size == 1:
                # Single item, keep it
                filtered_counts.append(chapter_counts[group_start])
            elif group_size == 2:
                # Two consecutive items, keep the higher one
                filtered_counts.append(chapter_counts[group_end])
            else:
                # Three or more consecutive items, keep first and last
                filtered_counts.append(chapter_counts[group_start])
                if chapter_counts[group_start] != chapter_counts[group_end]:  # Avoid duplicates
                    filtered_counts.append(chapter_counts[group_end])

            i += 1

        return sorted(filtered_counts)

    def get_clustered_cue_sets(
        self,
        silences: List[Tuple[float, float]],
        book_length: float,
    ) -> Dict[int, List[float]]:
        """Generate all possible cue set options using clustering"""

        self._notify_progress(Step.CUE_SET_SELECTION, 0, "Finalizing results...")

        k_clusters_min = 2
        k_clusters_max = min(15, len(silences))

        all_clusters: Dict[int, List[float]] = {}

        # Generate cue sets for different k values
        for k_clusters in range(k_clusters_min, k_clusters_max + 1):
            cue_set = self.generate_cue_set(silences, book_length, k_clusters)
            all_clusters.update(cue_set)

        # Convert to sorted list and filter consecutive counts
        cluster_list = [(k, v) for k, v in all_clusters.items()]
        cluster_list = sorted(cluster_list, key=lambda x: x[0])

        # Extract just the chapter counts and filter them
        chapter_counts = [k for k, v in cluster_list]
        filtered_counts = self._filter_consecutive_counts(chapter_counts)

        # Rebuild the dictionary with only the filtered counts
        filtered_clusters = {}
        for count in filtered_counts:
            for k, v in cluster_list:
                if k == count:
                    filtered_clusters[k] = v
                    break

        return filtered_clusters
