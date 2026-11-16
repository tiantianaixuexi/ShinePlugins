/**
 * Sidecar handshake.
 *
 * In production the Rust shell picks a free port, generates a one-shot token,
 * starts `python -m app` and exposes the pair through the `get_sidecar_info`
 * command. In a plain browser (vite dev) there is no Tauri runtime, so we fall
 * back to environment variables and the Vite `/api` proxy.
 */

import { invoke } from "@tauri-apps/api/core";

export interface SidecarInfo {
  baseUrl: string;
  token: string;
  port: number;
  pid: number;
  startedAt: string;
  status: string;
}

const env = import.meta.env;

/** Poll interval while Rust boots the Python sidecar. */
const READY_POLL_INTERVAL_MS = 200;
/** Must exceed the shell's HEALTH_TIMEOUT (45s) so we don't give up first. */
const READY_TIMEOUT_MS = 50_000;

let cached: SidecarInfo | null = null;
let inFlight: Promise<SidecarInfo> | null = null;

export function isRunningUnderTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function browserFallback(): SidecarInfo {
  return {
    baseUrl: (env.VITE_API_BASE_URL as string | undefined) ?? "",
    token: (env.VITE_API_TOKEN as string | undefined) ?? "",
    port: 0,
    pid: 0,
    startedAt: "",
    status: "external",
  };
}

function isReady(info: SidecarInfo): boolean {
  return info.status === "ready" && info.baseUrl.length > 0;
}

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * `get_sidecar_info` returns a `stopped` placeholder until the health probe
 * passes. Caching that placeholder would point every request at the Vite
 * proxy (empty baseUrl) forever, so keep polling until the real port arrives.
 */
async function waitForTauriSidecar(): Promise<SidecarInfo> {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const info = await invoke<SidecarInfo>("get_sidecar_info");
    if (isReady(info)) return info;
    await delay(READY_POLL_INTERVAL_MS);
  }
  throw new Error(`sidecar did not become ready within ${READY_TIMEOUT_MS}ms`);
}

export async function resolveSidecar(): Promise<SidecarInfo> {
  if (cached) return cached;
  if (inFlight) return inFlight;

  inFlight = (async (): Promise<SidecarInfo> => {
    if (isRunningUnderTauri()) {
      try {
        const info = await waitForTauriSidecar();
        cached = info;
        return info;
      } catch (error) {
        console.error("[sidecar] waiting for sidecar failed", error);
      }
    }
    cached = browserFallback();
    return cached;
  })();

  try {
    return await inFlight;
  } finally {
    inFlight = null;
  }
}

/** Forget the cached endpoint (used after a restart). */
export function resetSidecarCache(): void {
  cached = null;
  inFlight = null;
}