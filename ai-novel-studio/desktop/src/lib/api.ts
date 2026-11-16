/**
 * Typed client for the local FastAPI service.
 *
 * Every call goes through `request`, which attaches the sidecar bearer token
 * and normalises the backend's `{"error": {...}}` envelope into `ApiError`.
 */

import { resolveSidecar } from "@/lib/sidecar";
import type {
  Chapter,
  ChapterAcceptAi,
  ChapterAcceptAiResult,
  ChapterCreate,
  ChapterListItem,
  ChapterUpdate,
  ChapterVersion,
  HealthResponse,
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
  Project,
  ProjectCreate,
  ProjectStats,
  ProjectSummary,
  ProjectUpdate,
  StudioStats,
  SummaryResult,
  SystemInfo,
  Volume,
  VolumeCreate,
} from "@/types/api";

/**
 * Shown when the request never reached the backend: the dev proxy answers with
 * a bare 502/504, and a stopped sidecar makes fetch fail outright. Neither is a
 * provider problem, so it must not be reported as one.
 */
export const BACKEND_UNREACHABLE_MESSAGE =
  "无法连接后端服务。请确认 Python 后端已启动（桌面端会自动拉起；浏览器开发请先运行 scripts/dev-backend.ps1）。";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, code: string, status: number, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }

  get isAuthError(): boolean {
    return this.status === 401 || this.code === "auth_required";
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === "not_found";
  }

  get isConflict(): boolean {
    return this.status === 409 || this.code === "conflict";
  }

  /** The backend is down, not the model provider. */
  get isBackendUnreachable(): boolean {
    return this.code === "backend_unreachable";
  }
}

// Statuses the dev proxy or a gateway uses when the upstream is unavailable.
const UNREACHABLE_STATUS = new Set([502, 503, 504]);

/** True when a status means "the backend never answered", not "the model failed". */
export function isUnreachableStatus(status: number): boolean {
  return UNREACHABLE_STATUS.has(status);
}

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue>;

type Json = Record<string, unknown>;

function buildUrl(path: string, baseUrl: string, query?: QueryParams): string {
  const url = new URL(`${baseUrl}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    query?: QueryParams;
    headers?: HeadersInit;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const sidecar = await resolveSidecar();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  const hasBody = options.body !== undefined && options.body !== null;
  if (hasBody) headers.set("Content-Type", "application/json");
  if (sidecar.token) headers.set("Authorization", `Bearer ${sidecar.token}`);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, sidecar.baseUrl, options.query), {
      method: options.method ?? (hasBody ? "POST" : "GET"),
      headers,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (error) {
    // A cancelled request is a normal outcome (navigation, superseded query).
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(BACKEND_UNREACHABLE_MESSAGE, "backend_unreachable", 0);
  }

  if (!response.ok) {
    // The Vite dev proxy answers with a bare text/plain 502/504 when the
    // *backend* is down. That is not a provider failure and must not be
    // reported as one, so translate it before trying to read a JSON envelope.
    if (UNREACHABLE_STATUS.has(response.status)) {
      throw new ApiError(BACKEND_UNREACHABLE_MESSAGE, "backend_unreachable", response.status);
    }

    let code = "http_error";
    let message = `请求失败 (HTTP ${response.status})`;
    let details: unknown = null;
    try {
      const payload = (await response.json()) as {
        error?: { code?: string; message?: string; details?: unknown };
      };
      if (payload?.error) {
        code = payload.error.code ?? code;
        message = payload.error.message ?? message;
        details = payload.error.details ?? null;
      }
    } catch {
      // Non-JSON error body (proxy failure, closed sidecar, …)
    }
    throw new ApiError(message, code, response.status, details);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? (JSON.parse(text) as T) : (undefined as T));
}

/* -------------------------------------------------------------------------- */
/* Endpoints                                                                  */
/* -------------------------------------------------------------------------- */

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/api/health", { signal }),

  systemInfo: () => request<SystemInfo>("/api/system/info"),

  studioStats: () => request<StudioStats>("/api/system/stats"),

  projects: {
    list: (query?: QueryParams) => request<ProjectSummary[]>("/api/projects", { query }),

    get: (id: string) => request<Project>(`/api/projects/${encodeURIComponent(id)}`),

    create: (body: ProjectCreate) =>
      request<Project>("/api/projects", { method: "POST", body }),

    update: (id: string, body: ProjectUpdate) =>
      request<Project>(`/api/projects/${encodeURIComponent(id)}`, {
        method: "PUT",
        body,
      }),

    remove: (id: string, hard = false) =>
      request<void>(`/api/projects/${encodeURIComponent(id)}`, {
        method: "DELETE",
        query: { hard },
      }),

    duplicate: (id: string, name: string) =>
      request<Project>(`/api/projects/${encodeURIComponent(id)}/duplicate`, {
        method: "POST",
        body: { name } satisfies Json,
      }),

    stats: (id: string) =>
      request<ProjectStats>(`/api/projects/${encodeURIComponent(id)}/stats`),
  },

  volumes: {
    list: (projectId: string) => request<Volume[]>(path(projectId, "volumes")),
    create: (projectId: string, body: VolumeCreate) =>
      request<Volume>(path(projectId, "volumes"), { method: "POST", body }),
    update: (projectId: string, volumeId: string, body: Partial<Volume>) =>
      request<Volume>(path(projectId, "volumes", volumeId), { method: "PATCH", body }),
    remove: (projectId: string, volumeId: string) =>
      request<void>(path(projectId, "volumes", volumeId), { method: "DELETE" }),
  },

  chapters: {
    list: (projectId: string, query?: QueryParams) =>
      request<ChapterListItem[]>(path(projectId, "chapters"), { query }),

    create: (projectId: string, body: ChapterCreate) =>
      request<Chapter>(path(projectId, "chapters"), { method: "POST", body }),

    get: (projectId: string, chapterId: string) =>
      request<Chapter>(path(projectId, "chapters", chapterId)),

    update: (projectId: string, chapterId: string, body: ChapterUpdate) =>
      request<Chapter>(path(projectId, "chapters", chapterId), { method: "PUT", body }),

    remove: (projectId: string, chapterId: string) =>
      request<void>(path(projectId, "chapters", chapterId), { method: "DELETE" }),

    reorder: (projectId: string, chapterIds: string[]) =>
      request<ChapterListItem[]>(path(projectId, "chapters", "reorder"), {
        method: "POST",
        body: { chapter_ids: chapterIds },
      }),

    /**
     * Adopt AI text as the chapter body. The backend snapshots the current text
     * first, then records the accepted text as `source="ai"` with `task_id`.
     */
    acceptAi: (projectId: string, chapterId: string, body: ChapterAcceptAi) =>
      request<ChapterAcceptAiResult>(path(projectId, "chapters", chapterId, "accept-ai"), {
        method: "POST",
        body,
      }),

    versions: (projectId: string, chapterId: string) =>
      request<ChapterVersion[]>(path(projectId, "chapters", chapterId, "versions")),

    snapshot: (projectId: string, chapterId: string) =>
      request<ChapterVersion[]>(path(projectId, "chapters", chapterId, "versions"), {
        method: "POST",
      }),

    restore: (projectId: string, chapterId: string, versionId: string) =>
      request<Chapter>(
        path(projectId, "chapters", chapterId, "versions", versionId, "restore"),
        { method: "POST" },
      ),
  },

  ai: {
    /**
     * `POST /api/ai/summary/{chapter_id}` — distill one chapter into the L1
     * memory row. The backend caches by content fingerprint, so calling it with
     * `force: false` on an unchanged chapter costs nothing.
     */
    summarizeChapter: (projectId: string, chapterId: string, options?: { force?: boolean }) =>
      request<SummaryResult>(`/api/ai/summary/${encodeURIComponent(chapterId)}`, {
        method: "POST",
        body: { project_id: projectId, force: options?.force ?? false },
      }),
  },

  modelConfigs: {
    list: () => request<ModelConfig[]>("/api/model-configs"),

    create: (body: ModelConfigCreate) =>
      request<ModelConfig>("/api/model-configs", { method: "POST", body }),

    update: (id: string, body: ModelConfigUpdate) =>
      request<ModelConfig>(`/api/model-configs/${encodeURIComponent(id)}`, {
        method: "PUT",
        body,
      }),

    remove: (id: string) =>
      request<void>(`/api/model-configs/${encodeURIComponent(id)}`, { method: "DELETE" }),

    setDefault: (id: string) =>
      request<ModelConfig>(`/api/model-configs/${encodeURIComponent(id)}/default`, {
        method: "POST",
      }),
  },
};

/** Build `/api/projects/<id>/<segments…>` with every segment encoded. */
function path(projectId: string, ...segments: string[]): string {
  return [
    "/api/projects",
    encodeURIComponent(projectId),
    ...segments.map((segment) => encodeURIComponent(segment)),
  ].join("/");
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}