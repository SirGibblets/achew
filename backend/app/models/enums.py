from enum import Enum


class Step(str, Enum):
    ABS_SETUP = "abs_setup"  # Interactive
    LLM_SETUP = "llm_setup"  # Interactive
    ASR_SETUP = "asr_setup"  # Interactive
    IDLE = "idle"  # Interactive
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    FILE_PREP = "file_prep"
    SELECT_WORKFLOW = "select_workflow"  # Interactive
    AUDIO_ANALYSIS = "audio_analysis"
    VAD_PREP = "vad_prep"
    VAD_ANALYSIS = "vad_analysis"
    PARTIAL_SCAN_PREP = "partial_scan_prep"
    PARTIAL_AUDIO_ANALYSIS = "partial_audio_analysis"
    PARTIAL_VAD_ANALYSIS = "partial_vad_analysis"
    INITIAL_CHAPTER_SELECTION = "initial_chapter_selection"  # Interactive
    CONFIGURE_ASR = "configure_asr"  # Interactive
    AUDIO_EXTRACTION = "audio_extraction"
    TRIMMING = "trimming"
    ASR_PROCESSING = "asr_processing"
    CHAPTER_EDITING = "chapter_editing"  # Interactive
    AI_CLEANUP = "ai_cleanup"
    REVIEWING = "reviewing"  # Interactive
    COMPLETED = "completed"  # Interactive

    @property
    def ordinal(self):
        return list(self.__class__.__members__).index(self.name)


class RestartStep(str, Enum):
    """Potential restart points for session restart"""

    IDLE = Step.IDLE.value
    SELECT_WORKFLOW = Step.SELECT_WORKFLOW.value
    INITIAL_CHAPTER_SELECTION = Step.INITIAL_CHAPTER_SELECTION.value
    CONFIGURE_ASR = Step.CONFIGURE_ASR.value
    CHAPTER_EDITING = Step.CHAPTER_EDITING.value

    @property
    def ordinal(self):
        return list(self.__class__.__members__).index(self.name)
