import type { RefObject } from "react";
import { useRef } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  Check,
  Clock,
  History,
  Loader2,
  Save,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ChapterDraft, SaveState } from "@/hooks/use-chapter-draft";
import { errorMessage } from "@/lib/api";
import { countWords, readingMinutes } from "@/lib/utils";
import type { Chapter } from "@/types/api";

const SAVE_LABEL: Record<SaveState, string> = {
  idle: "已保存",
  pending: "待保存",
  saving: "保存中",
  saved: "已保存",
  error: "保存失败",
};

const SAVE_STYLE: Record<SaveState, string> = {
  idle: "text-muted-foreground",
  pending: "text-amber-600 dark:text-amber-400",
  saving: "text-sky-600 dark:text-sky-400",
  saved: "text-emerald-600 dark:text-emerald-400",
  error: "text-destructive",
};

function SaveIndicator({ state }: { state: SaveState }) {
  const Icon =
    state === "saving"
      ? Loader2
      : state === "error"
        ? TriangleAlert
        : state === "pending"
          ? Clock
          : Check;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] ${SAVE_STYLE[state]}`}>
      <Icon className={state === "saving" ? "size-3 animate-spin" : "size-3"} />
      {SAVE_LABEL[state]}
    </span>
  );
}

interface ChapterEditorProps {
  chapter: Chapter;
  draft: ChapterDraft;
  onOpenHistory: () => void;
  onSelectionChange: (text: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  aiOpen: boolean;
  onToggleAI: () => void;
}

/**
 * Manuscript surface. Presentational: all text state and autosave live in
 * `useChapterDraft`, so the AI panel can read and write the same buffer.
 *
 * A `<textarea>` is used on purpose: it preserves the author's raw text (no
 * HTML round-trip), behaves predictably with CJK input methods, and stays fast
 * on chapters of hundreds of kilobytes.
 */
export function ChapterEditor({
  chapter,
  draft,
  onOpenHistory,
  onSelectionChange,
  textareaRef,
  aiOpen,
  onToggleAI,
}: ChapterEditorProps) {
  const composing = useRef(false);
  const words = countWords(draft.content);

  const syncSelection = (element: HTMLTextAreaElement) => {
    const selected = element.value.slice(element.selectionStart, element.selectionEnd);
    onSelectionChange(selected);
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
        <Input
          value={draft.title}
          onChange={(event) => {
            draft.setTitle(event.target.value);
            if (!composing.current) draft.markDirty();
          }}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
            draft.markDirty();
          }}
          className="h-8 max-w-md border-transparent bg-transparent px-1 text-base font-medium shadow-none focus-visible:border-border"
          placeholder="章节标题"
        />
        <div className="ml-auto flex items-center gap-2">
          <SaveIndicator state={draft.saveState} />
          <Button
            variant={aiOpen ? "default" : "ghost"}
            size="sm"
            onClick={onToggleAI}
            title="AI 助手"
          >
            <Sparkles className="size-4" />
            AI
          </Button>
          <Button variant="ghost" size="sm" onClick={onOpenHistory}>
            <History className="size-4" />
            历史版本
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              void draft.snapshot().catch((error: unknown) => {
                toast.error("保存版本失败", { description: errorMessage(error) });
              });
            }}
          >
            <Save className="size-4" />
            存为版本
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <textarea
          ref={textareaRef}
          value={draft.content}
          onChange={(event) => {
            draft.setContent(event.target.value);
            if (!composing.current) draft.markDirty();
            syncSelection(event.target);
          }}
          onSelect={(event) => syncSelection(event.currentTarget)}
          onKeyUp={(event) => syncSelection(event.currentTarget)}
          onMouseUp={(event) => syncSelection(event.currentTarget)}
          onBlur={(event) => {
            // A selection that survives focus loss still applies.
            syncSelection(event.currentTarget);
          }}
          spellCheck={false}
          placeholder="从这里开始写……"
          className="prose-manuscript min-h-full w-full resize-none border-0 bg-transparent px-8 py-6 outline-none placeholder:text-muted-foreground/50 sm:px-12"
        />
      </div>

      <div className="flex items-center gap-3 border-t px-4 py-1.5 text-[11px] text-muted-foreground">
        <span className="tabular-nums">{words.toLocaleString("zh-CN")} 字</span>
        <span className="tabular-nums">约 {readingMinutes(words)} 分钟</span>
        {draft.saveState === "error" && (
          <span className="inline-flex items-center gap-1 text-destructive">
            <AlertCircle className="size-3" />
            修改尚未保存
          </span>
        )}
        {chapter.status !== "done" && (
          <Badge variant="outline" className="ml-auto">
            {chapter.status}
          </Badge>
        )}
      </div>
    </div>
  );
}