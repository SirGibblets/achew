export interface RealignmentData {
  original_timestamp: number;
  confidence: number;
  is_guess: boolean;
  /** Confirmed by the user: kept in place and used as ground truth when realignment is re-run */
  pinned: boolean;
}

export interface BasicChapter {
  timestamp: number;
  title: string;
}

export interface ChapterData {
  id: string;
  timestamp: number;
  transcript: string;
  title: string;
  deleted: boolean;
  realignment?: RealignmentData | null;
  selected: boolean;
}

export interface SelectionStats {
  total: number;
  selected: number;
  unselected: number;
}
