import { ApiError, BACKEND_UNREACHABLE_MESSAGE, isUnreachableStatus } from "@/lib/api";
import { resolveSidecar } from "@/lib/sidecar";
import type { AIRequest, AIResult } from "@/types/api";

export interface AIStreamHandlers {
  onDelta: (text: string) => void;
  onDone: (result: AIResult) => void;
  onError: (payload: { code: string; message: string }) => void;
}

interface SSEFrame {
  event: string;
  data: string;
}

function parseFrame(block: string): SSEFrame | null {
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
  const sidecar = await resolveSidecar();
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  });
  if (sidecar.token) headers.set("Authorization", `Bearer ${sidecar.token}`);

  let response: Response;
  try {
    response = await fetch(`${sidecar.baseUrl}/api/ai/${operation}/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    handlers.onError({
      code: "backend_unreachable",
      message: error instanceof ApiError ? error.message : BACKEND_UNREACHABLE_MESSAGE,
    });
    return;
  }

  if (!response.ok) {
    // A 502/504 here is the dev proxy saying the *backend* is gone, not the
    // provider refusing the request.
    if (isUnreachableStatus(response.status)) {
      handlers.onError({ code: "backend_unreachable", message: BACKEND_UNREACHABLE_MESSAGE });
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
    handlers.onError({ code, message });
    return;
  }

  if (!response.body) {
    handlers.onError({ code: "empty_response", message: "后端没有返回数据流。" });
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
        if (frame.event === "delta") {
          try {
            const parsed = JSON.parse(frame.data) as { text?: string };
            if (parsed.text) handlers.onDelta(parsed.text);
          } catch {
            // Ignore an incomplete frame; the next one will carry text.
          }
        } else if (frame.event === "done") {
          try {
            handlers.onDone(JSON.parse(frame.data) as AIResult);
          } catch {
            handlers.onError({ code: "bad_done_frame", message: "完成帧格式错误。" });
          }
          return;
        } else if (frame.event === "error") {
          try {
            const parsed = JSON.parse(frame.data) as { code?: string; message?: string };
            handlers.onError({
              code: parsed.code ?? "provider_error",
              message: parsed.message ?? "生成失败。",
            });
          } catch {
            handlers.onError({ code: "bad_error_frame", message: "错误帧格式错误。" });
          }
          return;
        }
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    if (error instanceof ApiError) {
      handlers.onError({ code: error.code, message: error.message });
      return;
    }
    handlers.onError({
      code: "stream_failed",
      message: error instanceof Error ? error.message : String(error),
    });
  } finally {
    reader.releaseLock();
  }
}