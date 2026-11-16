import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, errorMessage } from "@/lib/api";
import type { HealthResponse } from "@/types/api";

export type BackendStatus = "connecting" | "online" | "offline";

export const backendKeys = {
  all: ["backend"] as const,
  health: ["backend", "health"] as const,
  info: ["backend", "info"] as const,
  stats: ["backend", "stats"] as const,
};

/**
 * Poll the sidecar health endpoint. The desktop shell starts Python before
 * loading the UI, so this normally resolves on the first attempt; the retry
 * loop exists for the case where the process died or was restarted.
 */
export function useBackendHealth() {
  const query = useQuery({
    queryKey: backendKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: (query) => {
      const data = query.state.data as HealthResponse | undefined;
      return data?.status === "ok" ? 20_000 : 2_000;
    },
    retry: false,
    staleTime: 10_000,
  });

  const status: BackendStatus =
    query.isPending && !query.isError
      ? "connecting"
      : query.data?.status === "ok"
        ? "online"
        : "offline";

  return { ...query, status };
}

export function useSystemInfo() {
  return useQuery({
    queryKey: backendKeys.info,
    queryFn: () => api.systemInfo(),
    staleTime: 60_000,
  });
}

export function useStudioStats() {
  return useQuery({
    queryKey: backendKeys.stats,
    queryFn: () => api.studioStats(),
    staleTime: 30_000,
  });
}

/** Convenience helper for surfaces that only need a human-readable message. */
export function describeHealthError(error: unknown): string {
  return errorMessage(error);
}

export function useRecheckBackend() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const health = await api.health();
      queryClient.setQueryData(backendKeys.health, health);
      void queryClient.invalidateQueries({ queryKey: backendKeys.all });
      return health;
    },
  });
}