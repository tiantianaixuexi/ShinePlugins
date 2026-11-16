import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import { isRunningUnderTauri, resetSidecarCache, resolveSidecar } from "@/lib/sidecar";
import type { SidecarInfo } from "@/lib/sidecar";

const STOPPED: SidecarInfo = {
  baseUrl: "",
  token: "",
  port: 0,
  pid: 0,
  startedAt: "",
  status: "stopped",
};

const READY: SidecarInfo = {
  baseUrl: "http://127.0.0.1:19868",
  token: "tok",
  port: 19868,
  pid: 32696,
  startedAt: "2026-11-16T07:55:59Z",
  status: "ready",
};

function setTauri(enabled: boolean): void {
  if (enabled) Reflect.set(window, "__TAURI_INTERNALS__", {});
  else Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
}

beforeEach(() => {
  resetSidecarCache();
  invoke.mockReset();
  setTauri(true);
});

afterEach(() => {
  vi.useRealTimers();
  setTauri(false);
});

describe("resolveSidecar", () => {
  it("waits for ready instead of caching the stopped placeholder", async () => {
    vi.useFakeTimers();
    invoke.mockResolvedValueOnce(STOPPED).mockResolvedValueOnce(READY);

    const pending = resolveSidecar();
    await vi.advanceTimersByTimeAsync(250);

    await expect(pending).resolves.toEqual(READY);
    expect(invoke).toHaveBeenCalledTimes(2);
  });

  it("caches the ready endpoint for later calls", async () => {
    invoke.mockResolvedValue(READY);

    const first = await resolveSidecar();
    invoke.mockResolvedValue({ ...READY, port: 1234, baseUrl: "http://127.0.0.1:1234" });
    const second = await resolveSidecar();

    expect(second).toEqual(first);
    expect(invoke).toHaveBeenCalledTimes(1);
  });

  it("uses env config without invoking Tauri in a plain browser", async () => {
    setTauri(false);

    const info = await resolveSidecar();

    expect(isRunningUnderTauri()).toBe(false);
    expect(info.status).toBe("external");
    expect(invoke).not.toHaveBeenCalled();
  });
});
