import type { BasicChapter } from './chapter';

export type ChapterRefType = 'abs' | 'embedded' | 'audnexus' | 'file_data' | 'json' | 'csv' | 'cue' | 'snapshot';
export type TitleRefType = 'text' | 'epub' | 'custom';

interface ReferenceBase {
  id: string;
  name: string;
  short_name: string;
  description: string;
  metadata: Record<string, string>;
}

export interface ChapterReference extends ReferenceBase {
  type: ChapterRefType;
  chapters: BasicChapter[];
  duration: number;
}

export interface TitleReference extends ReferenceBase {
  type: TitleRefType;
  titles: string[];
}

export type Reference = ChapterReference | TitleReference;
