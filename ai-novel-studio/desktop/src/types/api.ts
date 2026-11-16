/**
 * Shapes returned by the Python backend.
 *
 * Keep these in sync with the Pydantic schemas in `backend/app/schemas/`.
 * Field names are camelCase on the wire (the frontend is the only consumer),
 * so the backend serialises with camelCase aliases where they differ.
 */

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface HealthResponse {
  status: "ok" | "starting";
  app: string;
  version: string;
  schema_version: number;
  environment: string;
  time: string;
}

export interface SystemInfo {
  app: string;
  version: string;
  schema_version: number;
  environment: string;
  data_dir: string;
  projects_dir: string;
  projects: number;
  auth_required: boolean;
}

export interface ProjectStats {
  volumes: number;
  chapters: number;
  words: number;
  characters: number;
  outlines: number;
  events: number;
  foreshadows: number;
  chunks: number;
  versions: number;
}

export type ProjectStatus = "active" | "archived" | "deleted" | string;

export interface Project {
  id: string;
  name: string;
  slug: string;
  novel_type: string;
  synopsis: string;
  target_word_count: number;
  target_chapter_count: number;
  writing_style: string;
  target_reader: string;
  language: string;
  author: string;
  status: ProjectStatus;
  path: string;
  schema_version: number;
  default_model_config_id: string | null;
  embedding_model_config_id: string | null;
  settings: Record<string, unknown>;
  row_version: number;
  created_at: string;
  updated_at: string;
  stats: ProjectStats;
}

export interface ProjectSummary {
  id: string;
  name: string;
  novel_type: string;
  status: ProjectStatus;
  language: string;
  target_word_count: number;
  target_chapter_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  novel_type?: string;
  synopsis?: string;
  target_word_count?: number;
  target_chapter_count?: number;
  writing_style?: string;
  target_reader?: string;
  language?: string;
  author?: string;
  default_model_config_id?: string | null;
  embedding_model_config_id?: string | null;
  settings?: Record<string, unknown>;
}

export type ProjectUpdate = Partial<Omit<ProjectCreate, "name">> & {
  name?: string;
  status?: string;
  row_version?: number;
};

export interface StudioTotals {
  projects: number;
  words: number;
  chapters: number;
  characters: number;
  chunks: number;
}

export interface StudioProjectRow {
  id: string;
  name: string;
  status: string;
  updated_at: string;
  words: number;
  chapters: number;
}

export interface StudioStats {
  totals: StudioTotals;
  projects: StudioProjectRow[];
}

/* -------------------------------------------------------------------------- */
/* Novels                                                                     */
/* -------------------------------------------------------------------------- */

export type ChapterStatus = "draft" | "writing" | "review" | "done" | "archived";

export interface Volume {
  id: string;
  project_id: string;
  title: string;
  summary: string;
  sort_order: number;
  word_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ChapterListItem {
  id: string;
  project_id: string;
  volume_id: string | null;
  title: string;
  sort_order: number;
  word_count: number;
  status: ChapterStatus;
  summary: string;
  /** Only meaningful when a list is fetched with `include_deleted=true`. */
  is_deleted?: boolean;
  deleted_at?: string | null;
  updated_at: string;
}

export interface Chapter extends ChapterListItem {
  content: string;
  row_version: number;
  created_at: string;
}

export interface ChapterVersion {
  id: string;
  chapter_id: string;
  version_no: number;
  title: string;
  word_count: number;
  source: "user" | "ai" | "import" | "restore" | string;
  /** Which AI task produced an `ai` version; null when it could not be told. */
  task_id?: string | null;
  note: string;
  created_at: string;
}

/** Body of `POST /chapters/{id}/accept-ai`. */
export interface ChapterAcceptAi {
  /** The full post-accept manuscript (the client already merged the AI text). */
  content: string;
  title?: string;
  task_id?: string | null;
  note?: string;
}

export interface ChapterAcceptAiResult {
  chapter: Chapter;
  version: ChapterVersion;
}

export interface ChapterCreate {
  title: string;
  volume_id?: string | null;
  content?: string;
  status?: ChapterStatus;
}

export interface ChapterUpdate {
  title?: string;
  volume_id?: string | null;
  content?: string;
  status?: ChapterStatus;
  sort_order?: number;
  snapshot?: boolean;
  row_version?: number;
}

export interface VolumeCreate {
  title: string;
  summary?: string;
}

/* -------------------------------------------------------------------------- */
/* Model configuration                                                        */
/* -------------------------------------------------------------------------- */

export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model_name: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  timeout_s: number;
  retry_count: number;
  context_window: number;
  max_output_tokens: number;
  supports_streaming: boolean;
  supports_json_mode: boolean;
  supports_vision: boolean;
  supports_tools: boolean;
  input_price_per_1m: number;
  output_price_per_1m: number;
  capabilities: Record<string, unknown>;
  notes: string;
  is_active: boolean;
  is_default: boolean;
  fallback_ids: string[];
  has_api_key: boolean;
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface ModelConfigCreate {
  name: string;
  provider?: string;
  base_url?: string;
  model_name: string;
  api_key?: string | null;
  temperature?: number;
  max_tokens?: number;
  context_window?: number;
  max_output_tokens?: number;
  supports_streaming?: boolean;
  supports_json_mode?: boolean;
  input_price_per_1m?: number;
  output_price_per_1m?: number;
  notes?: string;
  is_active?: boolean;
}

export type ModelConfigUpdate = Partial<ModelConfigCreate> & {
  row_version?: number;
  api_key?: string | null;
};

/* -------------------------------------------------------------------------- */
/* AI writing                                                                 */
/* -------------------------------------------------------------------------- */

export interface AIRequest {
  project_id: string;
  chapter_id?: string | null;
  /** Current manuscript text. Sent even when `chapter_id` is set so unsaved edits are used. */
  content?: string;
  /** Selected passage for expand / rewrite / polish. */
  selection?: string;
  instruction?: string;
  outline?: string;
  target_words?: number;
  model_config_id?: string | null;
  temperature?: number | null;
}

export interface AIResult {
  task_id: string;
  operation: string;
  text: string;
  model: string;
  prompt_key: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

/** Body of `POST /ai/summary/{chapter_id}/stream`. */
export interface SummaryStreamBody {
  project_id: string;
  /** Re-summarise even when a non-empty summary already exists. */
  force?: boolean;
}

/** Body of `POST /ai/outline/{chapter_id}/stream`. */
export interface OutlineStreamBody {
  project_id: string;
  /** Regenerate even when a usable outline row already exists. */
  force?: boolean;
  instruction?: string;
}

/** Token accounting attached to every streamed structured reply's `done`. */
export interface StreamUsage {
  input_tokens: number;
  output_tokens: number;
}

/** `done` payload of the streamed summary call. */
export interface SummaryStreamResult {
  chapter_id: string;
  summary: string;
  cached?: boolean;
  /** `"empty"` when the chapter body is blank and nothing was generated. */
  skipped?: string | null;
  usage?: StreamUsage;
}

/** `done` payload of the streamed outline call (one `outlines` row). */
export interface OutlineStreamResult {
  chapter_id: string;
  outline_id?: string;
  level?: string;
  parent_id?: string | null;
  title: string;
  goal: string;
  conflict: string;
  characters: string[];
  key_events: string[];
  twists?: string;
  foreshadows?: string[];
  ending?: string;
  target_word_count?: number;
  /** Verbatim reply, kept when the model never produced JSON. */
  content?: string;
  /** True when the model ignored the JSON instruction and the reply is raw text. */
  degraded: boolean;
  cached?: boolean;
  usage?: StreamUsage;
}

export interface AITaskSummary {
  id: string;
  project_id: string | null;
  kind: string;
  status: string;
  model_config_id: string | null;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  error: string | null;
  created_at: string;
}

export type AIOperation =
  | "outline"
  | "write"
  | "continue"
  | "expand"
  | "rewrite"
  | "polish"
  | "review";