export interface BookChapter {
  title: string;
  start: number;
  end: number;
}

export interface AudioFileMetadata {
  filename: string;
  ext: string;
  relPath: string;
  size: number;
}

export interface AudioFile {
  ino: string;
  mimeType: string;
  duration: number;
  metadata: AudioFileMetadata;
  chapters: BookChapter[];
}

export interface AudioInfo {
  codec?: string | null;
  container?: string | null;
  ffmpeg_output?: string | null;
}

export interface AuthorEntry {
  id?: string | null;
  name: string;
}

export interface SeriesDetails {
  id: string;
  name: string;
  sequence?: string | null;
}

export interface BookMetadata {
  title: string;
  subtitle?: string | null;
  authorName?: string;
  authors?: AuthorEntry[] | null;
  narratorName?: string;
  narrators?: string[] | null;
  seriesName?: string | null;
  seriesTitle?: string | null;
  series?: SeriesDetails[] | null;
  seriesOrder?: string | null;
  genres: string[];
  publishedYear?: string | null;
  description?: string | null;
  asin?: string | null;
  language?: string | null;
}

export interface BookMedia {
  metadata: BookMetadata;
  coverPath: string;
  duration?: number | null;
  audioFiles: AudioFile[];
  chapters: BookChapter[];
  numChapters?: number | null;
  numAudioFiles?: number | null;
}

export interface Book {
  id: string;
  libraryId?: string | null;
  addedAt: number;
  updatedAt: number;
  media: BookMedia;
  duration: number;
}

export interface BookSearchSeriesEntry {
  series: string;
  sequence?: string | null;
}

export interface BookSearchResult {
  title: string;
  author?: string | null;
  narrator?: string | null;
  narrators: string[];
  cover?: string | null;
  asin?: string | null;
  duration?: number | null;
  descriptionPlain?: string | null;
  series?: BookSearchSeriesEntry[] | null;
  matchConfidence?: number | null;
}
