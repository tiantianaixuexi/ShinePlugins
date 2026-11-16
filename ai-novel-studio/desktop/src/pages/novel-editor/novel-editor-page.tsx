import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Loader2, Plus, Trash2 } from "lucide-react";

import { AIPanel } from "@/components/editor/ai-panel";
import type { ApplyMode } from "@/lib/text-edit";
import { ChapterEditor } from "@/components/editor/chapter-editor";
import { ChapterTree } from "@/components/editor/chapter-tree";
import { VersionHistoryDialog } from "@/components/editor/version-history-dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useChapterDraft } from "@/hooks/use-chapter-draft";
import {
  novelKeys,
  useChapters,
  useChapter,
  useCreateChapter,
  useCreateVolume,
  useDeleteChapter,
  useVolumes,
} from "@/hooks/use-novel";
import { useProject } from "@/hooks/use-projects";
import { api, errorMessage } from "@/lib/api";
import { createSummaryTriggerLog } from "@/lib/summary-autosave";
import { applyText } from "@/lib/text-edit";
import type { Chapter } from "@/types/api";

function ProjectPicker() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-3 p-10 text-center">
      <div className="grid size-12 place-items-center rounded-xl border">
        <BookOpen className="size-5 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold">选择要创作的小说</h2>
      <p className="text-sm text-muted-foreground">
        编辑器需要绑定一个项目，才能读写对应的章节与记忆库。
      </p>
      <Button asChild variant="outline" size="sm">
        <Link to="/projects">前往项目管理</Link>
      </Button>
    </div>
  );
}

interface ChapterWorkspaceProps {
  projectId: string;
  chapter: Chapter;
  onOpenHistory: () => void;
  /** Called with the chapter the author just left, and the text they left it in. */
  onChapterLeft: (chapterId: string, content: string) => void;
}

/**
 * One chapter: manuscript + AI panel.
 *
 * Accepting AI text goes through the backend so the pre-accept manuscript is
 * snapshotted and the accepted text is stored as `source="ai"` with its task
 * id. Only if that call fails does the text land in the local buffer instead —
 * the author's words must never be dropped on a network hiccup.
 */
function ChapterWorkspace({
  projectId,
  chapter,
  onOpenHistory,
  onChapterLeft,
}: ChapterWorkspaceProps) {
  const draft = useChapterDraft(projectId, chapter);
  const queryClient = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [selection, setSelection] = useState("");
  const [aiOpen, setAiOpen] = useState(true);

  // Read through a ref so the unmount cleanup below sees the latest text and the
  // newest callback without re-registering on every keystroke.
  const leaveRef = useRef({ chapterId: chapter.id, content: draft.content, draft, onChapterLeft });
  leaveRef.current = { chapterId: chapter.id, content: draft.content, draft, onChapterLeft };

  // Leaving the chapter (the parent remounts this component under a new key) is
  // when its L1 summary is refreshed. The pending autosave is flushed first so
  // the server summarises the text the author actually left behind, not the
  // version from before the last keystrokes.
  useEffect(() => {
    return () => {
      const left = leaveRef.current;
      void left.draft.flush().finally(() => left.onChapterLeft(left.chapterId, left.content));
    };
  }, []);

  const handleApply = useCallback(
    async (text: string, mode: ApplyMode) => {
      const textarea = textareaRef.current;
      const range =
        textarea && mode !== "replace-all"
          ? { start: textarea.selectionStart ?? 0, end: textarea.selectionEnd ?? 0 }
          : null;

      const edit = applyText(draft.content, range, text, mode);

      try {
        // No task id reaches the panel (the SSE stream does not expose one), so
        // record the gap in the note instead of inventing one.
        const result = await api.chapters.acceptAi(projectId, chapter.id, {
          content: edit.content,
          title: draft.title || undefined,
          task_id: null,
          note: "AI 采纳（无 task_id）",
        });
        draft.adopt(result.chapter);
        void queryClient.invalidateQueries({
          queryKey: novelKeys.versions(projectId, chapter.id),
        });
        void queryClient.invalidateQueries({ queryKey: novelKeys.chapters(projectId) });
      } catch (error) {
        // Keep the text in the buffer; the autosave path will persist it as a
        // normal user edit.
        draft.setContent(edit.content);
        draft.markDirty();
        toast.warning("AI 结果未能记为 AI 版本", {
          description: `${errorMessage(error)}（已写入正文，将按普通编辑保存）`,
        });
      }

      // Put the caret after the inserted text so writing continues naturally.
      requestAnimationFrame(() => {
        const element = textareaRef.current;
        if (!element) return;
        element.focus();
        element.setSelectionRange(edit.caret, edit.caret);
        setSelection("");
      });
    },
    [chapter.id, draft, projectId, queryClient],
  );

  return (
    <>
      <ChapterEditor
        chapter={chapter}
        draft={draft}
        onOpenHistory={onOpenHistory}
        onSelectionChange={setSelection}
        textareaRef={textareaRef}
        aiOpen={aiOpen}
        onToggleAI={() => setAiOpen((open) => !open)}
      />
      {aiOpen && (
        <AIPanel
          projectId={projectId}
          chapterId={chapter.id}
          content={draft.content}
          selection={selection}
          onApply={handleApply}
          onClose={() => setAiOpen(false)}
        />
      )}
    </>
  );
}

function Workspace({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const volumesQuery = useVolumes(projectId);
  const chaptersQuery = useChapters(projectId);
  const createChapter = useCreateChapter(projectId);
  const createVolume = useCreateVolume(projectId);
  const deleteChapter = useDeleteChapter(projectId);

  const [activeChapterId, setActiveChapterId] = useState<string | null>(null);
  // One entry per (chapter, body) already sent this session. Lives here because
  // ChapterWorkspace remounts on every switch; a ref in the parent survives it.
  const summaryTriggers = useRef(createSummaryTriggerLog());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  // Bumped after a restore so the editor remounts with the restored text.
  const [chapterEpoch, setChapterEpoch] = useState(0);

  const chapterQuery = useChapter(projectId, activeChapterId);

  // Select the first chapter once the list arrives.
  useEffect(() => {
    if (activeChapterId) return;
    const first = chaptersQuery.data?.[0];
    if (first) setActiveChapterId(first.id);
  }, [activeChapterId, chaptersQuery.data]);

  // Drop the selection if the active chapter disappeared.
  useEffect(() => {
    if (!activeChapterId || chaptersQuery.isPending) return;
    const exists = chaptersQuery.data?.some((item) => item.id === activeChapterId);
    if (!exists) setActiveChapterId(chaptersQuery.data?.[0]?.id ?? null);
  }, [activeChapterId, chaptersQuery.data, chaptersQuery.isPending]);

  const handleCreateChapter = useCallback(
    async (volumeId: string | null) => {
      try {
        const chapter = await createChapter.mutateAsync({
          title: `第 ${(chaptersQuery.data?.length ?? 0) + 1} 章`,
          volume_id: volumeId,
        });
        setActiveChapterId(chapter.id);
      } catch (error) {
        toast.error("新建章节失败", { description: errorMessage(error) });
      }
    },
    [chaptersQuery.data?.length, createChapter],
  );

  const handleCreateVolume = useCallback(
    async (title: string) => {
      try {
        await createVolume.mutateAsync(title);
      } catch (error) {
        toast.error("新建分卷失败", { description: errorMessage(error) });
      }
    },
    [createVolume],
  );

  const handleDeleteChapter = useCallback(
    async (chapterId: string) => {
      try {
        await deleteChapter.mutateAsync(chapterId);
        if (activeChapterId === chapterId) {
          setActiveChapterId(chaptersQuery.data?.find((c) => c.id !== chapterId)?.id ?? null);
        }
        toast.success("章节已删除");
      } catch (error) {
        toast.error("删除失败", { description: errorMessage(error) });
      } finally {
        setDeleteTarget(null);
      }
    },
    [activeChapterId, chaptersQuery.data, deleteChapter],
  );

  const handleRestored = useCallback(async () => {
    await chapterQuery.refetch();
    setChapterEpoch((value) => value + 1);
  }, [chapterQuery]);

  /**
   * Refresh the L1 summary of the chapter the author just left.
   *
   * Fire-and-forget on purpose: it must never block the switch, and a failure is
   * not the author's problem — they never asked for it. No toast, console only.
   * The backend caches by content fingerprint, so the cost is at most one model
   * call per chapter *that actually changed*.
   */
  const handleChapterLeft = useCallback(
    (chapterId: string, content: string) => {
      if (!summaryTriggers.current.claim(chapterId, content)) return;
      void api.ai
        .summarizeChapter(projectId, chapterId, { force: false })
        .catch((error: unknown) => {
          console.warn("章节摘要自动更新失败（正文已保存，不影响写作）", error);
        });
    },
    [projectId],
  );

  const activeChapter = chapterQuery.data;

  if (project.isError) {
    return (
      <div className="p-10 text-center">
        <p className="text-sm text-destructive">{errorMessage(project.error)}</p>
        <Button asChild variant="outline" size="sm" className="mt-3">
          <Link to="/projects">返回项目列表</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/20 md:w-64">
        <ChapterTree
          volumes={volumesQuery.data ?? []}
          chapters={chaptersQuery.data ?? []}
          activeChapterId={activeChapterId}
          loading={chaptersQuery.isPending}
          onSelect={setActiveChapterId}
          onCreateChapter={(volumeId) => void handleCreateChapter(volumeId)}
          onCreateVolume={(title) => void handleCreateVolume(title)}
          onDeleteChapter={(chapterId) => setDeleteTarget(chapterId)}
          pending={createChapter.isPending || createVolume.isPending}
        />
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1">
        {chapterQuery.isPending && (
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-6">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="flex-1" />
          </div>
        )}

        {chapterQuery.isError && (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-10 text-center">
            <p className="text-sm text-destructive">{errorMessage(chapterQuery.error)}</p>
            <Button variant="outline" size="sm" onClick={() => void chapterQuery.refetch()}>
              重试
            </Button>
          </div>
        )}

        {!chapterQuery.isPending && !chapterQuery.isError && !activeChapter && (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-10 text-center">
            <div className="grid size-12 place-items-center rounded-xl border">
              <BookOpen className="size-5 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">还没有章节，创建第一章开始写作。</p>
            <Button size="sm" onClick={() => void handleCreateChapter(null)}>
              <Plus className="size-4" />
              新建章节
            </Button>
          </div>
        )}

        {activeChapter && (
          <ChapterWorkspace
            key={`${activeChapter.id}:${chapterEpoch}`}
            projectId={projectId}
            chapter={activeChapter}
            onOpenHistory={() => setHistoryOpen(true)}
            onChapterLeft={handleChapterLeft}
          />
        )}
      </div>

      {activeChapter && historyOpen && (
        <VersionHistoryDialog
          projectId={projectId}
          chapterId={activeChapter.id}
          open={historyOpen}
          onOpenChange={setHistoryOpen}
          onRestored={() => void handleRestored()}
        />
      )}

      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="size-4 text-destructive" />
              删除这一章？
            </AlertDialogTitle>
            <AlertDialogDescription>
              章节会从列表中移除，历史版本仍保留在数据库中。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteTarget && void handleDeleteChapter(deleteTarget)}
            >
              {deleteChapter.isPending && <Loader2 className="size-4 animate-spin" />}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export function NovelEditorPage() {
  const [params] = useSearchParams();
  const projectId = params.get("project") ?? undefined;
  if (!projectId) return <ProjectPicker />;
  return <Workspace projectId={projectId} />;
}

/** Convenience route: /projects/:projectId/editor */
export function NovelEditorByIdPage() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) return <ProjectPicker />;
  return <Workspace projectId={projectId} />;
}