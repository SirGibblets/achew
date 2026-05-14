import type { ChapterData } from './chapter';
import type { ExistingCueSource, ExistingTitleSource } from './sources';

export const WSMessageType = {
  STATUS: 'status',
  PROGRESS_UPDATE: 'progress_update',
  STEP_CHANGE: 'step_change',
  CHAPTER_UPDATE: 'chapter_update',
  HISTORY_UPDATE: 'history_update',
  BATCH_OPERATION: 'batch_operation',
  TRANSCRIBING_UPDATE: 'transcribing_update',
  SOURCES_UPDATE: 'sources_update',
  ERROR: 'error',
  SELECTION_STATS: 'selection_stats',
} as const;

export type WSMessageType = (typeof WSMessageType)[keyof typeof WSMessageType];

export interface ProgressUpdateData {
  step: string;
  percent: number;
  message: string;
  details: Record<string, unknown>;
}

export interface StepChangeData {
  old_step: string;
  new_step: string;
  cue_sources?: ExistingCueSource[];
  title_sources?: ExistingTitleSource[];
  restart_options?: string[];
  audio_unsupported_codec?: boolean;
  chapter_id?: string;
  open_tab?: string;
}

export interface ChapterUpdateData {
  chapters: ChapterData[];
  total_count: number;
  selected_count: number;
}

export interface HistoryUpdateData {
  can_undo: boolean;
  can_redo: boolean;
  current_description?: string | null;
}

export interface SelectionStatsData {
  total: number;
  selected: number;
  unselected: number;
}

export interface SourcesUpdateData {
  cue_sources?: ExistingCueSource[];
  title_sources?: ExistingTitleSource[];
}

export interface TranscribingUpdateData {
  statuses: Record<string, string>;
}

export interface ErrorData {
  message: string;
  details?: string | null;
  code?: string | null;
  recoverable?: boolean;
}

export interface StatusData {
  type?: string;
  book?: unknown;
  [key: string]: unknown;
}

export interface BatchOperationData {
  operation: string;
  affected_count: number;
  description: string;
  success: boolean;
}

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  data: T;
  timestamp?: string;
}
