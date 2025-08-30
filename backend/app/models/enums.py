from enum import Enum


class Step(str, Enum):
    ABS_SETUP = "abs_setup"  # Interactive
    LLM_SETUP = "llm_setup"  # Interactive
    IDLE = "idle"  # Interactive
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    FILE_PREP = "file_prep"
    SELECT_CUE_SOURCE = "select_cue_source"  # Interactive
    AUDIO_ANALYSIS = "audio_analysis"
    VAD_PREP = "vad_prep"
    VAD_ANALYSIS = "vad_analysis"
    CUE_SET_SELECTION = "cue_set_selection"  # Interactive
    AUDIO_EXTRACTION = "audio_extraction"
    CONFIGURE_ASR = "configure_asr"  # Interactive
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
    SELECT_CUE_SOURCE = Step.SELECT_CUE_SOURCE.value
    CUE_SET_SELECTION = Step.CUE_SET_SELECTION.value
    CONFIGURE_ASR = Step.CONFIGURE_ASR.value
    CHAPTER_EDITING = Step.CHAPTER_EDITING.value

    @property
    def ordinal(self):
        return list(self.__class__.__members__).index(self.name)
