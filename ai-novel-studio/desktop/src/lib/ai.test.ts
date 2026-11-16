import { afterEach, describe, expect, it, vi } from "vitest";

import { streamAI } from "@/lib/ai";
import type { AIResult } from "@/types/api";

const DONE: AIResult = {
  task_id: "tsk_1",
  operation: "polish",
  text: "你好",
  model: "test-model",
  prompt_key: "edit.polish",
  input_tokens: 11,
  output_tokens: 2,
  cost: 0,
};

function sseResponse(frames: string[], init: ResponseInit = { status: 200 }) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(frames.join("")));
      controller.close();
    },
  });
  return new Response(stream, init);
}

function collect() {
  const state = { deltas: [] as string[], done: null as AIResult | null, error: null as { code: string; message: string } | null };
  return {
    state,
    handlers: {
      onDelta: (text: string) => state.deltas.push(text),
      onDone: (result: AIResult) => {
        state.done = result;
      },
      onError: (payload: { code: string; message: string }) => {
        state.error = payload;
      },
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamAI", () => {
  it("parses delta and done frames", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          'event: delta\ndata: {"text":"你"}\n\n',
          'event: delta\ndata: {"text":"好"}\n\n',
          `event: done\ndata: ${JSON.stringify(DONE)}\n\n`,
        ]),
      ),
    );

    const { state, handlers } = collect();
    await streamAI("polish", { project_id: "p", chapter_id: "c" }, handlers);

    expect(state.deltas.join("")).toBe("你好");
    expect(state.done?.output_tokens).toBe(2);
    expect(state.error).toBeNull();
  });

  it("handles frames split across chunk boundaries", async () => {
    // A delta frame arrives in two network chunks.
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('event: delta\ndata: {"text":"你'));
        controller.enqueue(encoder.encode('好"}\n\n'));
        controller.enqueue(encoder.encode(`event: done\ndata: ${JSON.stringify(DONE)}\n\n`));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

    const { state, handlers } = collect();
    await streamAI("polish", { project_id: "p" }, handlers);

    expect(state.deltas.join("")).toBe("你好");
    expect(state.done).not.toBeNull();
  });

  it("reports error frames without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          'event: error\ndata: {"code":"provider_auth_failed","message":"API Key 无效"}\n\n',
        ]),
      ),
    );

    const { state, handlers } = collect();
    await streamAI("polish", { project_id: "p" }, handlers);

    expect(state.error?.code).toBe("provider_auth_failed");
    expect(state.error?.message).toBe("API Key 无效");
  });

  it("turns an HTTP error body into an error event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "no_model", message: "还没有配置模型" } }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const { state, handlers } = collect();
    await streamAI("polish", { project_id: "p" }, handlers);

    expect(state.error?.code).toBe("no_model");
    expect(state.error?.message).toBe("还没有配置模型");
  });

  it("ignores malformed frames and keeps reading", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          "event: delta\ndata: not-json\n\n",
          'event: delta\ndata: {"text":"好"}\n\n',
          `event: done\ndata: ${JSON.stringify(DONE)}\n\n`,
        ]),
      ),
    );

    const { state, handlers } = collect();
    await streamAI("polish", { project_id: "p" }, handlers);

    expect(state.deltas.join("")).toBe("好");
    expect(state.done).not.toBeNull();
  });
});