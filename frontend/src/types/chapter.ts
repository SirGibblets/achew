export interface RealignmentData {
  original_timestamp: number;
  confidence: number;
  is_guess: boolean;
}

export interface ChapterData {
  id: string;
  timestamp: number;
  asr_title: string;
  current_title: string;
  deleted: boolean;
  audio_segment_path?: string | null;
  realignment?: RealignmentData | null;
  selected: boolean;
}

export interface SelectionStats {
  total: number;
  selected: number;
  unselected: number;
}
