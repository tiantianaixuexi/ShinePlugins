import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useQueryClient } from "@tanstack/react-query";

import { ApiError, api, errorMessage } from "@/lib/api";
import { novelKeys } from "@/hooks/use-novel";
import type { Chapter } from "@/types/api";

export type SaveState = "idle" | "pending" | "saving" | "saved" | "error";

export interface ChapterDraft {
  title: string;
  content: string;
  saveState: SaveState;
  setTitle: (value: string) => void;
  setContent: (value: string) => void;
  /** Call after an external change (AI apply, undo) to schedule a save. */
  markDirty: () => void;
  /** Save immediately; resolves once the server has acknowledged. */
  flush: () => Promise<void>;
  /** Force a history snapshot of the current text. */
  snapshot: () => Promise<void>;
  /**
   * Adopt a chapter the server already persisted (e.g. after accepting AI
   * text): refreshes the row version so autosave cannot 409, without marking
   * the buffer dirty.
   */
  adopt: (chapter: Chapter) => void;
}

/**
 * Owns the chapter's editable state and its debounced autosave.
 *
 * Kept separate from the view so the AI panel and the editor can read and write
 * the same buffer without prop-drilling through a textarea.
 */
export function useChapterDraft(projectId: string, chapter: Chapter): ChapterDraft {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(chapter.title);
  const [content, setContent] = useState(chapter.content);
  const [saveState, setSaveState] = useState<SaveState>("idle");

  const rowVersion = useRef(chapter.row_version);
  const dirty = useRef(false);
  const stateRef = useRef({ title: chapter.title, content: chapter.content });
  stateRef.current = { title, content };

  const inflight = useRef<Promise<void> | null>(null);

  const runSave = useCallback(async () => {
    if (!dirty.current) return;
    dirty.current = false;
    setSaveState("saving");
    try {
      const snapshot = stateRef.current;
      const saved = await api.chapters.update(projectId, chapter.id, {
        title: snapshot.title || "未命名章节",
        content: snapshot.content,
        row_version: rowVersion.current,
      });
      rowVersion.current = saved.row_version;
      setSaveState("saved");
      queryClient.setQueryData(novelKeys.chapter(projectId, chapter.id), saved);
      void queryClient.invalidateQueries({ queryKey: novelKeys.chapters(projectId) });
    } catch (error) {
      dirty.current = true;
      setSaveState("error");
      if (error instanceof ApiError && error.code === "conflict") {
        toast.error("章节已被其他地方修改", {
          description: "已重新载入最新内容，请再次确认修改。",
        });
        await queryClient.invalidateQueries({
          queryKey: novelKeys.chapter(projectId, chapter.id),
        });
        return;
      }
      toast.error("保存失败", { description: errorMessage(error) });
    }
  }, [chapter.id, projectId, queryClient]);

  // Resolves only once the server has acknowledged — including a save that was
  // already in flight when the caller asked (the summary trigger needs exactly
  // that guarantee). A second concurrent PUT for the same `row_version` would 409.
  const flush = useCallback(async () => {
    if (inflight.current) await inflight.current;
    if (!dirty.current) return;
    const task = runSave();
    inflight.current = task;
    try {
      await task;
    } finally {
      if (inflight.current === task) inflight.current = null;
    }
  }, [runSave]);

  const markDirty = useCallback(() => {
    dirty.current = true;
    setSaveState("pending");
  }, []);

  // Debounced autosave.
  useEffect(() => {
    if (!dirty.current) return;
    const timer = window.setTimeout(() => void flush(), 1200);
    return () => window.clearTimeout(timer);
  }, [title, content, flush]);

  // Flush when the author switches chapters or closes the window.
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (dirty.current) void flush();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      if (dirty.current) void flush();
    };
  }, [flush]);

  // Ctrl/Cmd+S saves immediately.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void flush();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [flush]);

  const snapshot = useCallback(async () => {
    await flush();
    await api.chapters.snapshot(projectId, chapter.id);
    void queryClient.invalidateQueries({
      queryKey: novelKeys.versions(projectId, chapter.id),
    });
  }, [chapter.id, flush, projectId, queryClient]);

  const adopt = useCallback(
    (next: Chapter) => {
      dirty.current = false;
      rowVersion.current = next.row_version;
      stateRef.current = { title: next.title, content: next.content };
      setTitle(next.title);
      setContent(next.content);
      setSaveState("saved");
      queryClient.setQueryData(novelKeys.chapter(projectId, next.id), next);
    },
    [projectId, queryClient],
  );

  return {
    title,
    content,
    saveState,
    setTitle,
    setContent,
    markDirty,
    flush,
    snapshot,
    adopt,
  };
}