import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ChapterCreate } from "@/types/api";

export const novelKeys = {
  all: ["novel"] as const,
  volumes: (projectId: string) => [...novelKeys.all, "volumes", projectId] as const,
  chapters: (projectId: string) => [...novelKeys.all, "chapters", projectId] as const,
  chapter: (projectId: string, chapterId: string) =>
    [...novelKeys.all, "chapter", projectId, chapterId] as const,
  versions: (projectId: string, chapterId: string) =>
    [...novelKeys.all, "versions", projectId, chapterId] as const,
};

export function useVolumes(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? novelKeys.volumes(projectId) : ["novel", "volumes", "none"],
    queryFn: () => api.volumes.list(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useChapters(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? novelKeys.chapters(projectId) : ["novel", "chapters", "none"],
    queryFn: () => api.chapters.list(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useChapter(projectId: string | undefined, chapterId: string | null) {
  return useQuery({
    queryKey:
      projectId && chapterId
        ? novelKeys.chapter(projectId, chapterId)
        : ["novel", "chapter", "none"],
    queryFn: () => api.chapters.get(projectId!, chapterId!),
    enabled: Boolean(projectId && chapterId),
  });
}

export function useChapterVersions(projectId: string, chapterId: string | null) {
  return useQuery({
    queryKey: chapterId ? novelKeys.versions(projectId, chapterId) : ["novel", "versions", "none"],
    queryFn: () => api.chapters.versions(projectId, chapterId!),
    enabled: Boolean(chapterId),
  });
}

function useInvalidateNovel(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: novelKeys.volumes(projectId) });
    void queryClient.invalidateQueries({ queryKey: novelKeys.chapters(projectId) });
    void queryClient.invalidateQueries({ queryKey: ["projects", "stats", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
  };
}

export function useCreateChapter(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateNovel(projectId);
  return useMutation({
    mutationFn: (payload: ChapterCreate) => api.chapters.create(projectId, payload),
    onSuccess: (chapter) => {
      queryClient.setQueryData(novelKeys.chapter(projectId, chapter.id), chapter);
      invalidate();
    },
  });
}

export function useDeleteChapter(projectId: string) {
  const invalidate = useInvalidateNovel(projectId);
  return useMutation({
    mutationFn: (chapterId: string) => api.chapters.remove(projectId, chapterId),
    onSuccess: invalidate,
  });
}

export function useCreateVolume(projectId: string) {
  const invalidate = useInvalidateNovel(projectId);
  return useMutation({
    mutationFn: (title: string) => api.volumes.create(projectId, { title }),
    onSuccess: invalidate,
  });
}

export function useSnapshotChapter(projectId: string, chapterId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.chapters.snapshot(projectId, chapterId),
    onSuccess: (versions) => {
      queryClient.setQueryData(novelKeys.versions(projectId, chapterId), versions);
    },
  });
}

export function useRestoreChapter(projectId: string, chapterId: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateNovel(projectId);
  return useMutation({
    mutationFn: (versionId: string) => api.chapters.restore(projectId, chapterId, versionId),
    onSuccess: (chapter) => {
      queryClient.setQueryData(novelKeys.chapter(projectId, chapter.id), chapter);
      void queryClient.invalidateQueries({ queryKey: novelKeys.versions(projectId, chapterId) });
      invalidate();
    },
  });
}