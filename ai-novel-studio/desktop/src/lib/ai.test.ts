import { afterEach, describe, expect, it, vi } from "vitest";

import { applyStreamOutcome, streamAI, streamSummary } from "@/lib/ai";
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

describe("applyStreamOutcome", () => {
  it("drops everything received before a reset and keeps only the new round", () => {
    let buffer = "";
    for (const outcome of [
      { kind: "delta", text: "好的，" },
      { kind: "delta", text: "我这就写。" },
      { kind: "reset" },
      { kind: "delta", text: '{"summary":"雨夜客栈。"}' },
    ] as const) {
      buffer = applyStreamOutcome(buffer, outcome);
    }

    expect(buffer).toBe('{"summary":"雨夜客栈。"}');
  });

  it("keeps accumulating deltas when no reset arrives", () => {
    let buffer = "";
    for (const text of ["你", "好", "，", "世界"]) {
      buffer = applyStreamOutcome(buffer, { kind: "delta", text });
    }

    expect(buffer).toBe("你好，世界");
    // Non-text outcomes must never disturb what is already buffered.
    expect(applyStreamOutcome(buffer, { kind: "skip" })).toBe("你好，世界");
    expect(applyStreamOutcome(buffer, { kind: "done", data: {} })).toBe("你好，世界");
  });
});

describe("streamSummary", () => {
  it("honours the reset frame so the repaired reply replaces the first attempt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: delta\ndata: {"text":"好的，"}\n\n',
        'event: delta\ndata: {"text":"我这就写。"}\n\n',
        "event: reset\ndata: {}\n\n",
        `event: delta\ndata: ${JSON.stringify({ text: '{"summary":"雨夜客栈。"}' })}\n\n`,
        `event: done\ndata: ${JSON.stringify({
          chapter_id: "c",
          summary: "雨夜客栈。",
          cached: false,
          usage: { input_tokens: 18, output_tokens: 14 },
        })}\n\n`,
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    let buffer = "";
    let resets = 0;
    const done: { summary: string }[] = [];
    await streamSummary(
      "c",
      { project_id: "p", force: true },
      {
        onDelta: (text) => {
          buffer = applyStreamOutcome(buffer, { kind: "delta", text });
        },
        onReset: () => {
          resets += 1;
          buffer = applyStreamOutcome(buffer, { kind: "reset" });
        },
        onDone: (payload) => {
          done.push(payload as { summary: string });
        },
        onError: (payload) => {
          throw new Error(`${payload.code}: ${payload.message}`);
        },
      },
    );

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/ai/summary/c/stream");
    expect(resets).toBe(1);
    // The prose from the first attempt is gone: only the repair survives, so the
    // buffer is still valid JSON.
    expect(buffer).not.toContain("我这就写");
    expect(JSON.parse(buffer)).toEqual({ summary: "雨夜客栈。" });
    expect(done).toHaveLength(1);
  });

  it("concatenates a normal structured stream without any reset", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          `event: delta\ndata: ${JSON.stringify({ text: '{"summary":' })}\n\n`,
          `event: delta\ndata: ${JSON.stringify({ text: '"雨夜。"}' })}\n\n`,
          `event: done\ndata: ${JSON.stringify({ chapter_id: "c", summary: "雨夜。" })}\n\n`,
        ]),
      ),
    );

    let buffer = "";
    let resets = 0;
    await streamSummary(
      "c",
      { project_id: "p" },
      {
        onDelta: (text) => {
          buffer = applyStreamOutcome(buffer, { kind: "delta", text });
        },
        onReset: () => {
          resets += 1;
        },
        onDone: () => undefined,
        onError: (payload) => {
          throw new Error(`${payload.code}: ${payload.message}`);
        },
      },
    );

    expect(resets).toBe(0);
    expect(JSON.parse(buffer)).toEqual({ summary: "雨夜。" });
  });
});