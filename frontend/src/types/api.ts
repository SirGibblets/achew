import type { AudioInfo, Book } from './book';
import type { BasicChapter, ChapterData, SelectionStats } from './chapter';
import type { ChapterReference, TitleReference } from './references';

export interface ProgressState {
  step: string;
  percent: number;
  message: string;
  details: Record<string, unknown>;
}

export interface PipelineState {
  step: string;
  item_id: string;
  progress: ProgressState;
  selection_stats: SelectionStats;
  can_undo: boolean;
  can_redo: boolean;
  chapter_refs?: ChapterReference[];
  title_refs?: TitleReference[];
  book?: Book | null;
  restart_options?: string[];
  audio_unsupported_codec?: boolean;
  audio_info?: AudioInfo | null;
}

export interface StatusResponse {
  has_pipeline: boolean;
  item_id?: string;
  step?: string;
  version?: string | null;
  build_meta?: string | null;
}

export interface ABSConfigResponse {
  url: string;
  api_key: string;
  validated: boolean;
  last_validated?: string | null;
}

export interface ChaptersResponse {
  chapters: ChapterData[];
  selection_stats: SelectionStats;
}

export interface ChapterExportResult {
  data: string;
  filename: string;
  mimeType: string;
}

export interface AIOptions {
  inferOpeningCredits: boolean;
  inferEndCredits: boolean;
  deselectNonChapters: boolean;
  keepDeselectedTitles: boolean;
  usePreferredTitles: boolean;
  preferredTitlesRef: string;
  additionalInstructions: string;
  provider_id: string;
  model_id: string;
}

export interface ASRPreferences {
  service_id: string;
  variant_id?: string;
  language?: string;
}

export interface ASRServiceVariant {
  id: string;
  name: string;
  [key: string]: unknown;
}

export interface ASRServiceOption {
  service_id: string;
  name: string;
  desc: string;
  uses_gpu: boolean;
  supports_bias_words: boolean;
  priority: number;
  variants: ASRServiceVariant[];
}

export interface ASRPreferencesResponse {
  available_services: ASRServiceOption[];
  current_service: string;
  current_variant: string;
  current_language: string;
  book_language: string | null;
}

export interface ASROptions {
  trim: boolean;
  use_bias_words: boolean;
  bias_words: string;
  segment_length: number;
}

export interface ASROptionsResponse {
  options: ASROptions;
}

export interface EditorSettings {
  show_formatted_time?: boolean;
  show_fractional_seconds?: boolean;
  hide_transcriptions?: boolean;
  tab_navigation?: boolean;
  [key: string]: unknown;
}

export interface EditorSettingsUpdateResponse {
  message: string;
  editor_settings: EditorSettings;
}

export interface LLMSetupField {
  name: string;
  label?: string;
  type?: string;
  placeholder?: string;
  required?: boolean;
  help_text?: string;
  help_url?: string;
  [key: string]: unknown;
}

export interface LLMProvider {
  id: string;
  name: string;
  description: string;
  instructions?: string | null;
  setup_fields: LLMSetupField[];
  is_available: boolean;
  is_enabled: boolean;
  is_configured: boolean;
  is_recommended: boolean;
  validation_status: string;
  validation_message?: string | null;
  config_changed: boolean;
  [key: string]: unknown;
}

export interface LLMProvidersResponse {
  providers: LLMProvider[];
}

export interface LLMModel {
  id: string;
  name: string;
  description?: string | null;
  context_length?: number | null;
  supports_streaming?: boolean;
  [key: string]: unknown;
}

export interface LLMModelsResponse {
  models: LLMModel[];
}

export interface LLMProviderValidationResponse {
  valid: boolean;
  message: string;
}

export interface LLMProviderResponse {
  success: boolean;
  message: string;
  provider_state?: Record<string, unknown> | null;
}

export interface ABSLibrary {
  id: string;
  name: string;
  mediaType?: string;
  [key: string]: unknown;
}

export interface AudnexusProviderOption {
  value: string;
  label: string;
}

export interface BookSearchPayload {
  provider: string;
  title?: string;
  author?: string;
  id?: string;
}

export interface ValidateItemResponse {
  valid: boolean;
  book_title?: string | null;
  book_duration?: number | null;
  cover_url?: string | null;
  file_count?: number | null;
  error_message?: string | null;
}

export interface DetectedCueEntry {
  timestamp: number;
  gap: number;
}

export interface DetectedCuesResponse {
  detected_cues: DetectedCueEntry[];
  book_duration: number;
  chapter_refs: ChapterReference[];
}

export interface NearbyCuesResponse {
  cues: DetectedCueEntry[];
}

export interface AddOptionsResponse {
  min_timestamp: number;
  max_timestamp: number;
  detected_cues: DetectedCueEntry[];
  chapter_refs: Record<string, BasicChapter[]>;
  deleted: BasicChapter[];
  allow_normal_scan: boolean;
  allow_vad_scan: boolean;
}

export interface SelectedCuesResponse {
  cues: number[];
}

export interface PreassignedTitle {
  cue_index: number;
  title: string;
}

export interface CancelResponse {
  action: string;
  [key: string]: unknown;
}

export interface ReferencesResponse {
  chapter_refs: ChapterReference[];
  title_refs: TitleReference[];
}

export interface CustomInstruction {
  id: string;
  text: string;
  checked: boolean;
  order: number;
}

export interface CustomInstructionsResponse {
  instructions: CustomInstruction[];
}

export interface BatchOperationResponse {
  message: string;
  affected_chapters: number;
}

export interface ShiftOperation {
  chapter_id: string;
  new_timestamp: number;
}

export interface ApplyTitleMapping {
  chapter_id: string;
  new_title: string;
}
