# Seconds to pull chapter start back from detected silence end.
CHAPTER_START_PADDING = 1 / 3

# Minimum length in seconds for a trimmed audio segment.
MIN_TRIMMED_SEGMENT_LENGTH = 1.1

# Minimum seconds of silence to be considered a valid chapter boundary.
MIN_SILENCE_DURATION = 1.0

# Minimum gap in seconds between adjacent audio segments extracted for ASR.
MIN_SEGMENT_GAP = 0.5

# Maximum number of jittered retries when ASR returns empty.
MAX_JITTER_RETRIES = 3

# Maximum seconds to crop from the start of audio for ASR jitter retries.
MAX_JITTER_CROP = 0.1

# Ignore silences within this many seconds of the book's end to prevent false positives.
BOOK_END_IGNORE_WINDOW = 1.5

# Default padding used to determine the extraction window for realignment
REALIGN_PADDING_DEFAULT = 15.0

# The padding used to determine the extraction window for thorough/expanded realignment
REALIGN_PADDING_EXPANDED = 180.0

# VAD speech-probability threshold (0-1) for entering a speech segment
VAD_SPEECH_THRESHOLD = 0.6

# VAD hysteresis floor (0-1) for leaving a speech segment once in it
VAD_NEG_SPEECH_THRESHOLD = 0.55

# VAD minimum speech-segment length in milliseconds
VAD_MIN_SPEECH_DURATION_MS = 250
