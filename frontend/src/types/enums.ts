export const Step = {
  MIGRATION_FAILED: 'migration_failed',
  WELCOME: 'welcome',
  ABS_SETUP: 'abs_setup',
  LLM_SETUP: 'llm_setup',
  ASR_SETUP: 'asr_setup',
  IDLE: 'idle',
  VALIDATING: 'validating',
  DOWNLOADING: 'downloading',
  FILE_PREP: 'file_prep',
  SELECT_WORKFLOW: 'select_workflow',
  AUDIO_ANALYSIS: 'audio_analysis',
  VAD_PREP: 'vad_prep',
  VAD_ANALYSIS: 'vad_analysis',
  PARTIAL_SCAN_PREP: 'partial_scan_prep',
  PARTIAL_AUDIO_ANALYSIS: 'partial_audio_analysis',
  PARTIAL_VAD_ANALYSIS: 'partial_vad_analysis',
  INITIAL_CHAPTER_SELECTION: 'initial_chapter_selection',
  CONFIGURE_ASR: 'configure_asr',
  AUDIO_EXTRACTION: 'audio_extraction',
  TRIMMING: 'trimming',
  ASR_PROCESSING: 'asr_processing',
  CHAPTER_EDITING: 'chapter_editing',
  AI_CLEANUP: 'ai_cleanup',
  REVIEWING: 'reviewing',
  COMPLETED: 'completed',
} as const;

export type Step = (typeof Step)[keyof typeof Step];

export const RestartStep = {
  IDLE: Step.IDLE,
  SELECT_WORKFLOW: Step.SELECT_WORKFLOW,
  INITIAL_CHAPTER_SELECTION: Step.INITIAL_CHAPTER_SELECTION,
  CONFIGURE_ASR: Step.CONFIGURE_ASR,
  CHAPTER_EDITING: Step.CHAPTER_EDITING,
} as const;

export type RestartStep = (typeof RestartStep)[keyof typeof RestartStep];
