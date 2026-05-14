export type CueSourceType = 'abs' | 'embedded' | 'audnexus' | 'file_data' | 'json' | 'csv' | 'cue' | 'snapshot';
export type TitleSourceType = 'text' | 'epub' | 'custom';

export interface ExistingCue {
  timestamp: number;
  title: string;
}

interface SourceBase {
  id: string;
  name: string;
  short_name: string;
  description: string;
  metadata: Record<string, string>;
}

export interface ExistingCueSource extends SourceBase {
  type: CueSourceType;
  cues: ExistingCue[];
  duration: number;
}

export interface ExistingTitleSource extends SourceBase {
  type: TitleSourceType;
  titles: string[];
}

export type ExistingSource = ExistingCueSource | ExistingTitleSource;
