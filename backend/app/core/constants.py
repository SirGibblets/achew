# Seconds to pull chapter start back from detected silence end.
CHAPTER_START_PADDING = 1/3

# Minimum length in seconds for a trimmed audio segment.
MIN_TRIMMED_SEGMENT_LENGTH = 1.1

# Minimum seconds of silence to be considered a valid chapter boundary.
MIN_SILENCE_DURATION = 1.0

# Minimum gap in seconds between adjacent audio segments extracted for ASR.
MIN_SEGMENT_GAP = 0.5

# Drop silences ending within this many seconds of the book's end.
END_OF_BOOK_EXCLUSION_ZONE = 5.0

# Maximum number of jittered retries when ASR returns empty.
MAX_JITTER_RETRIES = 3

# Maximum seconds to crop from the start of audio for ASR jitter retries.
MAX_JITTER_CROP = 0.1