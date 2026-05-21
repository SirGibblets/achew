import type { ChapterData } from './chapter';
import type { ChapterReference, TitleReference } from './references';

export const WSMessageType = {
  STATUS: 'status',
  PROGRESS_UPDATE: 'progress_update',
  STEP_CHANGE: 'step_change',
  CHAPTER_UPDATE: 'chapter_update',
  HISTORY_UPDATE: 'history_update',
  BATCH_OPERATION: 'batch_operation',
  TRANSCRIBING_UPDATE: 'transcribing_update',
  REFERENCES_UPDATE: 'references_update',
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
  chapter_refs?: ChapterReference[];
  title_refs?: TitleReference[];
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

export interface ReferencesUpdateData {
  chapter_refs?: ChapterReference[];
  title_refs?: TitleReference[];
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
