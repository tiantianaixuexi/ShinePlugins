import { ApiError, BACKEND_UNREACHABLE_MESSAGE, isUnreachableStatus } from "@/lib/api";
import { resolveSidecar } from "@/lib/sidecar";
import type {
  AIRequest,
  AIResult,
  OutlineStreamBody,
  OutlineStreamResult,
  SummaryStreamBody,
  SummaryStreamResult,
} from "@/types/api";

export interface AIStreamHandlers {
  onDelta: (text: string) => void;
  /**
   * The server is regenerating the reply from scratch (the JSON repair retry).
   * Everything received so far must be thrown away before the next `delta`.
   */
  onReset?: () => void;
  onDone: (result: AIResult) => void;
  onError: (payload: { code: string; message: string }) => void;
}

/** Handlers for the structured (summary / outline) streams. */
export interface StructuredStreamHandlers<T> {
  onDelta: (text: string) => void;
  onReset?: () => void;
  onDone: (payload: T) => void;
  onError: (payload: { code: string; message: string }) => void;
}

export interface SSEFrame {
  event: string;
  data: string;
}

/** What one SSE frame means, once decoded. Pure, so it is unit-testable. */
export type StreamOutcome =
  | { kind: "delta"; text: string }
  | { kind: "reset" }
  | { kind: "done"; data: unknown }
  | { kind: "error"; code: string; message: string }
  | { kind: "skip" };

export function parseFrame(block: string): SSEFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/**
 * Decode one frame into an outcome.
 *
 * `reset` exists because the backend repairs a non-JSON structured reply by
 * re-sending the whole answer: without it a client that simply concatenates
 * deltas ends up with two replies glued together, i.e. invalid JSON.
 */
export function interpretFrame(frame: SSEFrame): StreamOutcome {
  switch (frame.event) {
    case "delta": {
      try {
        const parsed = JSON.parse(frame.data) as { text?: unknown };
        if (typeof parsed?.text === "string" && parsed.text) {
          return { kind: "delta", text: parsed.text };
        }
      } catch {
        // Incomplete or garbled frame: the next one carries text.
      }
      return { kind: "skip" };
    }
    case "reset":
      return { kind: "reset" };
    case "done": {
      try {
        return { kind: "done", data: JSON.parse(frame.data) };
      } catch {
        return { kind: "error", code: "bad_done_frame", message: "完成帧格式错误。" };
      }
    }
    case "error": {
      try {
        const parsed = JSON.parse(frame.data) as { code?: string; message?: string };
        return {
          kind: "error",
          code: parsed.code ?? "provider_error",
          message: parsed.message ?? "生成失败。",
        };
      } catch {
        return { kind: "error", code: "bad_error_frame", message: "错误帧格式错误。" };
      }
    }
    default:
      return { kind: "skip" };
  }
}

/**
 * Accumulate streamed text. `reset` clears the buffer, so the repaired reply
 * replaces the first attempt instead of being appended to it.
 */
export function applyStreamOutcome(buffer: string, outcome: StreamOutcome): string {
  if (outcome.kind === "delta") return buffer + outcome.text;
  if (outcome.kind === "reset") return "";
  return buffer;
}

/** Visitor over outcomes; return `true` to stop reading the stream. */
type OutcomeVisitor = (outcome: StreamOutcome) => boolean;

async function openStream(
  path: string,
  body: unknown,
  signal: AbortSignal | undefined,
  visit: OutcomeVisitor,
): Promise<void> {
  const sidecar = await resolveSidecar();
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  });
  if (sidecar.token) headers.set("Authorization", `Bearer ${sidecar.token}`);

  let response: Response;
  try {
    response = await fetch(`${sidecar.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    visit({
      kind: "error",
      code: "backend_unreachable",
      message: error instanceof ApiError ? error.message : BACKEND_UNREACHABLE_MESSAGE,
    });
    return;
  }

  if (!response.ok) {
    // A 502/504 here is the dev proxy saying the *backend* is gone, not the
    // provider refusing the request.
    if (isUnreachableStatus(response.status)) {
      visit({ kind: "error", code: "backend_unreachable", message: BACKEND_UNREACHABLE_MESSAGE });
      return;
    }

    let code = "provider_error";
    let message = `生成失败 (HTTP ${response.status})`;
    try {
      const payload = (await response.json()) as {
        error?: { code?: string; message?: string };
      };
      if (payload?.error) {
        code = payload.error.code ?? code;
        message = payload.error.message ?? message;
      }
    } catch {
      // Non-JSON body: keep the generic message.
    }
    visit({ kind: "error", code, message });
    return;
  }

  if (!response.body) {
    visit({ kind: "error", code: "empty_response", message: "后端没有返回数据流。" });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const frame = parseFrame(block);
        if (!frame) continue;
        if (visit(interpretFrame(frame))) return;
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    if (error instanceof ApiError) {
      visit({ kind: "error", code: error.code, message: error.message });
      return;
    }
    visit({
      kind: "error",
      code: "stream_failed",
      message: error instanceof Error ? error.message : String(error),
    });
  } finally {
    reader.releaseLock();
  }
}

/**
 * Run a writing operation and stream the text back.
 *
 * `EventSource` cannot POST, so this reads the response body directly and
 * decodes the SSE frames produced by `sse-starlette`.
 */
export async function streamAI(
  operation: string,
  body: AIRequest,
  handlers: AIStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await openStream(`/api/ai/${operation}/stream`, body, signal, (outcome) => {
    switch (outcome.kind) {
      case "delta":
        handlers.onDelta(outcome.text);
        return false;
      case "reset":
        handlers.onReset?.();
        return false;
      case "done":
        handlers.onDone(outcome.data as AIResult);
        return true;
      case "error":
        handlers.onError({ code: outcome.code, message: outcome.message });
        return true;
      default:
        return false;
    }
  });
}

/**
 * `POST /ai/summary/{chapter_id}/stream` — streaming twin of the summary call.
 * The `done` payload is the non-streaming result plus `usage`.
 */
export async function streamSummary(
  chapterId: string,
  body: SummaryStreamBody,
  handlers: StructuredStreamHandlers<SummaryStreamResult>,
  signal?: AbortSignal,
): Promise<void> {
  await openStream(
    `/api/ai/summary/${encodeURIComponent(chapterId)}/stream`,
    body,
    signal,
    (outcome) => {
      switch (outcome.kind) {
        case "delta":
          handlers.onDelta(outcome.text);
          return false;
        case "reset":
          handlers.onReset?.();
          return false;
        case "done":
          handlers.onDone(outcome.data as SummaryStreamResult);
          return true;
        case "error":
          handlers.onError({ code: outcome.code, message: outcome.message });
          return true;
        default:
          return false;
      }
    },
  );
}

/**
 * `POST /ai/outline/{chapter_id}/stream` — outline generation is the slowest
 * call in the product, so it is the one that most needs progress frames.
 */
export async function streamOutline(
  chapterId: string,
  body: OutlineStreamBody,
  handlers: StructuredStreamHandlers<OutlineStreamResult>,
  signal?: AbortSignal,
): Promise<void> {
  await openStream(
    `/api/ai/outline/${encodeURIComponent(chapterId)}/stream`,
    body,
    signal,
    (outcome) => {
      switch (outcome.kind) {
        case "delta":
          handlers.onDelta(outcome.text);
          return false;
        case "reset":
          handlers.onReset?.();
          return false;
        case "done":
          handlers.onDone(outcome.data as OutlineStreamResult);
          return true;
        case "error":
          handlers.onError({ code: outcome.code, message: outcome.message });
          return true;
        default:
          return false;
      }
    },
  );
}
