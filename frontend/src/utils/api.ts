import type {
  ABSLibrary,
  AddOptionsResponse,
  AIOptions,
  ApplyTitleMapping,
  ASROptions,
  ASROptionsResponse,
  ASRPreferencesResponse,
  AudnexusProviderOption,
  BatchOperationResponse,
  Book,
  BookSearchResult,
  CancelResponse,
  ChapterExportResult,
  ChaptersResponse,
  CustomInstruction,
  CustomInstructionsResponse,
  DetectedCuesResponse,
  EditorSettings,
  EditorSettingsUpdateResponse,
  ChapterReference,
  LLMModelsResponse,
  LLMProviderResponse,
  LLMProvidersResponse,
  LLMProviderValidationResponse,
  NearbyCuesResponse,
  PipelineState,
  PreassignedTitle,
  SelectedCuesResponse,
  ShiftOperation,
  ReferencesResponse,
  StatusResponse,
  TitleReference,
  ValidateItemResponse,
} from '../types';
import type { ChapterData } from '../types/chapter';

const API_BASE = window.location.origin;

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: BodyInit | Record<string, unknown> | null;
}

export class APIError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown = null) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.details = details;
  }
}

async function apiRequest<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}/api${endpoint}`;

  const { body, headers, ...rest } = options;
  const isFormBody = body instanceof FormData || body instanceof Blob;
  const finalHeaders: Record<string, string> = {
    ...(isFormBody ? {} : { 'Content-Type': 'application/json' }),
    ...(headers as Record<string, string> | undefined),
  };

  let finalBody: BodyInit | null | undefined;
  if (body && typeof body === 'object' && !isFormBody) {
    finalBody = JSON.stringify(body);
  } else {
    finalBody = body as BodyInit | null | undefined;
  }

  const config: RequestInit = {
    ...rest,
    headers: finalHeaders,
    body: finalBody,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      let errorDetails: unknown = null;

      try {
        const errorData = (await response.json()) as { detail?: string; message?: string };
        errorMessage = errorData.detail ?? errorData.message ?? errorMessage;
        errorDetails = errorData;
      } catch {
        errorMessage = (await response.text()) || errorMessage;
      }

      throw new APIError(errorMessage, response.status, errorDetails);
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return (await response.json()) as T;
    }

    return (await response.text()) as unknown as T;
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }

    const message = error instanceof Error ? error.message : String(error);
    throw new APIError(`Network error: ${message}`, 0, { originalError: error });
  }
}

export const session = {
  create(itemId: string) {
    return apiRequest<{ session_id?: string; [k: string]: unknown }>('/pipeline', {
      method: 'POST',
      body: { item_id: itemId },
    });
  },

  get() {
    return apiRequest<PipelineState>('/pipeline/state');
  },

  delete() {
    return apiRequest<unknown>('/pipeline', { method: 'DELETE' });
  },

  submit() {
    return apiRequest<unknown>('/pipeline/submit', { method: 'POST' });
  },

  gotoReview() {
    return apiRequest<unknown>('/pipeline/goto-review', { method: 'POST' });
  },

  getStatus() {
    return apiRequest<StatusResponse>('/status');
  },

  startWorkflow(workflow: string, refId?: string, dramatized?: boolean) {
    return apiRequest<unknown>('/pipeline/start-workflow', {
      method: 'POST',
      body: { workflow, ref_id: refId, dramatized },
    });
  },

  getDetectedCues() {
    return apiRequest<DetectedCuesResponse>('/pipeline/detected-cues');
  },

  selectInitialChapters(timestamps: number[], includeUnaligned: string[] = []) {
    return apiRequest<unknown>('/pipeline/select-initial-chapters', {
      method: 'POST',
      body: { timestamps, include_unaligned: includeUnaligned },
    });
  },

  validateItem(itemId: string) {
    return apiRequest<ValidateItemResponse>('/validate-item', {
      method: 'POST',
      body: { item_id: itemId },
    });
  },

  restart(restartAtStep: string) {
    return apiRequest<unknown>('/pipeline/restart', {
      method: 'POST',
      body: { restart_step: restartAtStep },
    });
  },

  getASROptions() {
    return apiRequest<ASROptionsResponse>('/pipeline/asr-options');
  },

  updateASROptions(options: ASROptions | Record<string, unknown>) {
    return apiRequest<unknown>('/pipeline/asr-options', {
      method: 'PUT',
      body: options as Record<string, unknown>,
    });
  },

  cancel() {
    return apiRequest<CancelResponse>('/pipeline/cancel', { method: 'POST' });
  },

  configureASR(action: string, preassignedTitles: PreassignedTitle[] = []) {
    return apiRequest<unknown>('/pipeline/configure-asr', {
      method: 'POST',
      body: { action, preassigned_titles: preassignedTitles },
    });
  },

  getSelectedCues() {
    return apiRequest<SelectedCuesResponse>('/pipeline/selected-cues');
  },
};

export const chapters = {
  getAll() {
    return apiRequest<ChaptersResponse>('/chapters');
  },

  updateTitle(chapterId: string, title: string) {
    return apiRequest<unknown>(`/chapters/${chapterId}/title`, {
      method: 'PUT',
      body: { title },
    });
  },

  updateTimestamp(chapterId: string, timestamp: number) {
    return apiRequest<unknown>(`/chapters/${chapterId}/timestamp`, {
      method: 'PUT',
      body: { timestamp },
    });
  },

  setSelection({ chapterIds = null, selected }: { chapterIds?: string[] | null; selected: boolean }) {
    return apiRequest<BatchOperationResponse>('/chapters/selection', {
      method: 'PUT',
      body: { chapter_ids: chapterIds, selected },
    });
  },

  delete(chapterId: string) {
    return apiRequest<unknown>(`/chapters/${chapterId}`, { method: 'DELETE' });
  },

  undo() {
    return apiRequest<unknown>('/chapters/undo', { method: 'POST', body: {} });
  },

  redo() {
    return apiRequest<unknown>('/chapters/redo', { method: 'POST', body: {} });
  },

  async export(format: string): Promise<ChapterExportResult> {
    const response = await fetch(`${API_BASE}/api/chapters/export/${format}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new APIError(`Failed to export ${format}`, response.status);
    }

    const contentDisposition = response.headers.get('content-disposition');
    let filename = `chapters.${format}`;
    if (contentDisposition) {
      const filenameMatch = /filename="(.+)"/.exec(contentDisposition);
      if (filenameMatch) {
        filename = filenameMatch[1] ?? filename;
      }
    }

    const contentType = response.headers.get('content-type');
    const data = await response.text();

    return { data, filename, mimeType: contentType ?? 'text/plain' };
  },

  exportAsSnapshot() {
    return apiRequest<ChapterReference>('/chapters/export/snapshot', { method: 'POST', body: {} });
  },

  getAddOptions(chapterId: string) {
    return apiRequest<AddOptionsResponse>(`/chapters/add-options/${chapterId}`);
  },

  getNearbyCues(chapterId: string) {
    return apiRequest<NearbyCuesResponse>(`/chapters/${chapterId}/nearby-cues`);
  },

  startPartialScan(chapterId: string, scanType: string) {
    return apiRequest<unknown>(`/chapters/${chapterId}/partial-scan`, {
      method: 'POST',
      body: { scan_type: scanType },
    });
  },

  add(chapterData: Partial<ChapterData> & Record<string, unknown>) {
    return apiRequest<unknown>('/chapters', { method: 'POST', body: chapterData });
  },

  deleteBySelection(target: string) {
    return apiRequest<BatchOperationResponse>('/chapters/delete-by-selection', {
      method: 'POST',
      body: { target },
    });
  },

  shiftTimestamps(shifts: ShiftOperation[]) {
    return apiRequest<BatchOperationResponse>('/chapters/shift-timestamps', {
      method: 'POST',
      body: { shifts },
    });
  },

  applyTitles(mappings: ApplyTitleMapping[]) {
    return apiRequest<BatchOperationResponse>('/chapters/apply-titles', {
      method: 'POST',
      body: { mappings },
    });
  },

  transcribe(chapterId: string) {
    return apiRequest<unknown>(`/chapters/${chapterId}/transcribe`, { method: 'POST' });
  },

  transcribeSelected() {
    return apiRequest<unknown>('/chapters/transcribe-selected', { method: 'POST' });
  },

  cancelTranscriptions() {
    return apiRequest<unknown>('/chapters/cancel-transcriptions', { method: 'POST' });
  },
};

export const batch = {
  processSelected(aiOptions: Partial<AIOptions> = {}) {
    return apiRequest<BatchOperationResponse>('/chapters/ai-cleanup', {
      method: 'POST',
      body: { ai_options: aiOptions },
    });
  },

  getAIOptions() {
    return apiRequest<AIOptions>('/chapters/ai-options');
  },

  updateAIOptions(aiOptions: Partial<AIOptions>) {
    return apiRequest<AIOptions>('/chapters/ai-options', {
      method: 'PUT',
      body: aiOptions,
    });
  },

  getCustomInstructions() {
    return apiRequest<CustomInstructionsResponse>('/chapters/custom-instructions');
  },

  saveCustomInstructions(instructions: CustomInstruction[]) {
    return apiRequest<CustomInstructionsResponse>('/chapters/custom-instructions', {
      method: 'PUT',
      body: { instructions },
    });
  },
};

export const audio = {
  getStreamUrl(): string {
    const timestamp = Date.now();
    return `${API_BASE}/api/audio/stream?t=${timestamp}`;
  },
};

export const health = {
  check() {
    return apiRequest<unknown>('/health', {
      method: 'GET',
      headers: {},
    });
  },
};

export function handleApiError(error: unknown): string {
  console.error('API Error:', error);

  if (error instanceof APIError) {
    if (error.message) {
      return error.message;
    }
    switch (error.status) {
      case 401:
        return 'Authentication required. Please check your API credentials.';
      case 403:
        return 'Access forbidden. Please check your permissions.';
      case 404:
        return 'Resource not found. It may have been deleted or moved.';
      case 409:
        return 'Conflict. The resource may be in use or have been modified.';
      case 422:
        return 'Invalid input data. Please check your request.';
      case 429:
        return 'Too many requests. Please wait before trying again.';
      case 500:
        return 'Server error. Please try again later.';
      case 503:
        return 'Service unavailable. The server may be under maintenance.';
      default:
        return 'An unexpected error occurred.';
    }
  }

  return 'Network error. Please check your connection and try again.';
}

export const config = {
  getASRPreferences() {
    return apiRequest<ASRPreferencesResponse>('/asr/preferences');
  },

  setASRPreferences(serviceId: string, variantId = '', language = '') {
    return apiRequest<unknown>('/asr/preferences', {
      method: 'POST',
      body: { service_id: serviceId, variant_id: variantId, language },
    });
  },

  getEditorSettings() {
    return apiRequest<EditorSettings>('/config/editor-settings');
  },

  updateEditorSettings(settings: Partial<EditorSettings>) {
    return apiRequest<EditorSettingsUpdateResponse>('/config/editor-settings', {
      method: 'PATCH',
      body: settings,
    });
  },
};

export const llm = {
  getProviders() {
    return apiRequest<LLMProvidersResponse>('/llm/providers');
  },

  getModels(providerId: string) {
    return apiRequest<LLMModelsResponse>(`/llm/providers/${providerId}/models`);
  },

  validateProvider(providerId: string, config: Record<string, unknown>) {
    return apiRequest<LLMProviderValidationResponse>(`/llm/providers/${providerId}/validate`, {
      method: 'POST',
      body: { provider_id: providerId, config },
    });
  },

  updateProviderConfig(providerId: string, config: Record<string, unknown>) {
    return apiRequest<LLMProviderResponse>(`/llm/providers/${providerId}/config`, {
      method: 'POST',
      body: { provider_id: providerId, config },
    });
  },

  setProviderEnabled(providerId: string, enabled: boolean) {
    return apiRequest<LLMProviderResponse>(`/llm/providers/${providerId}/enable`, {
      method: 'POST',
      body: { enabled },
    });
  },

  cancelProviderChanges(providerId: string) {
    return apiRequest<LLMProviderResponse>(`/llm/providers/${providerId}/cancel`, { method: 'POST' });
  },

  getProviderConfig(providerId: string) {
    return apiRequest<Record<string, unknown>>(`/llm/providers/${providerId}/config`, { method: 'GET' });
  },
};

export const audiobookshelf = {
  getLibraries() {
    return apiRequest<ABSLibrary[]>('/audiobookshelf/libraries');
  },

  searchLibrary(libraryId: string, query: string) {
    return apiRequest<Book[]>(`/audiobookshelf/libraries/${libraryId}/search?q=${encodeURIComponent(query)}`);
  },

  getLibraryItems(libraryId: string, refresh = false) {
    const params = new URLSearchParams();
    if (refresh) {
      params.append('refresh', 'true');
    }

    const queryString = params.toString();
    const url = `/audiobookshelf/libraries/${libraryId}/items${queryString ? `?${queryString}` : ''}`;

    return apiRequest<Book[]>(url);
  },

  clearAllCache() {
    return apiRequest<unknown>('/audiobookshelf/cache/clear', { method: 'POST' });
  },
};

export const references = {
  getAll() {
    return apiRequest<ReferencesResponse>('/pipeline/references');
  },

  upload(formData: FormData) {
    return apiRequest<ChapterReference | TitleReference>('/pipeline/references/upload', {
      method: 'POST',
      body: formData,
    });
  },

  addAudnexus(asin: string, provider: string) {
    return apiRequest<ChapterReference>('/pipeline/references/audnexus', {
      method: 'POST',
      body: { asin, provider },
    });
  },

  delete(refId: string) {
    return apiRequest<unknown>(`/pipeline/references/${encodeURIComponent(refId)}`, {
      method: 'DELETE',
    });
  },

  updateTitles(refId: string, titles: string[]) {
    return apiRequest<TitleReference>(`/pipeline/references/${encodeURIComponent(refId)}/titles`, {
      method: 'PUT',
      body: { titles },
    });
  },
};

export const abs = {
  getProviders() {
    return apiRequest<AudnexusProviderOption[]>('/audiobookshelf/providers');
  },

  searchBooks({
    provider,
    title = '',
    author = '',
    id = '',
  }: {
    provider: string;
    title?: string;
    author?: string;
    id?: string;
  }) {
    const params = new URLSearchParams({ provider });
    if (title) params.append('title', title);
    if (author) params.append('author', author);
    if (id) params.append('id', id);
    return apiRequest<BookSearchResult[]>(`/audiobookshelf/search/books?${params.toString()}`);
  },
};

export const api = {
  session,
  chapters,
  batch,
  audio,
  health,
  config,
  llm,
  audiobookshelf,
  references,
  abs,
};

export default api;
