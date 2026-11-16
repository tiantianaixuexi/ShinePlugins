import { useMemo, useState } from "react";
import { BookOpen, ChevronDown, Plus, ScrollText, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatNumber } from "@/lib/utils";
import type { ChapterListItem, Volume } from "@/types/api";

interface ChapterTreeProps {
  volumes: Volume[];
  chapters: ChapterListItem[];
  activeChapterId: string | null;
  loading: boolean;
  onSelect: (chapterId: string) => void;
  onCreateChapter: (volumeId: string | null) => void;
  onCreateVolume: (title: string) => void;
  onDeleteChapter: (chapterId: string) => void;
  pending: boolean;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-muted-foreground/50",
  writing: "bg-amber-500",
  review: "bg-sky-500",
  done: "bg-emerald-500",
  archived: "bg-muted-foreground/30",
};

function ChapterRow({
  chapter,
  active,
  onSelect,
  onDelete,
}: {
  chapter: ChapterListItem;
  active: boolean;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <div
      className={cn(
        "group flex items-center gap-1 rounded-md pr-1 transition-colors",
        active ? "bg-primary/15" : "hover:bg-muted/60",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(chapter.id)}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-sm",
          active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground",
        )}
      >
        <span
          className={cn("size-1.5 shrink-0 rounded-full", STATUS_STYLE[chapter.status] ?? "")}
          aria-hidden
        />
        <span className={cn("min-w-0 flex-1 truncate", active && "font-medium")}>
          {chapter.title}
        </span>
        <span className="shrink-0 text-[10px] tabular-nums opacity-60">
          {formatNumber(chapter.word_count)}
        </span>
      </button>
      {onDelete && (
        <button
          type="button"
          title="删除本章"
          onClick={() => onDelete(chapter.id)}
          className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
        >
          <Trash2 className="size-3" />
        </button>
      )}
    </div>
  );
}

export function ChapterTree({
  volumes,
  chapters,
  activeChapterId,
  loading,
  onSelect,
  onCreateChapter,
  onCreateVolume,
  onDeleteChapter,
  pending,
}: ChapterTreeProps) {
  const [addingVolume, setAddingVolume] = useState(false);
  const [volumeTitle, setVolumeTitle] = useState("");

  const grouped = useMemo(() => {
    const byVolume = new Map<string | null, ChapterListItem[]>();
    for (const chapter of chapters) {
      const list = byVolume.get(chapter.volume_id) ?? [];
      list.push(chapter);
      byVolume.set(chapter.volume_id, list);
    }
    return byVolume;
  }, [chapters]);

  const orphans = grouped.get(null) ?? [];

  const submitVolume = async () => {
    const title = volumeTitle.trim();
    if (!title) {
      setAddingVolume(false);
      return;
    }
    await onCreateVolume(title);
    setVolumeTitle("");
    setAddingVolume(false);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-2 py-1.5">
        <span className="px-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          章节
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            title="新建分卷"
            disabled={pending}
            onClick={() => setAddingVolume((value) => !value)}
          >
            <Plus className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            title="新建章节"
            disabled={pending}
            onClick={() => onCreateChapter(null)}
          >
            <ScrollText className="size-3.5" />
          </Button>
        </div>
      </div>

      {addingVolume && (
        <div className="flex items-center gap-1 border-b p-2">
          <Input
            autoFocus
            className="h-7 text-xs"
            placeholder="分卷标题，回车创建"
            value={volumeTitle}
            onChange={(event) => setVolumeTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void submitVolume();
              }
              if (event.key === "Escape") setAddingVolume(false);
            }}
          />
          <Button size="sm" variant="ghost" onClick={() => void submitVolume()}>
            创建
          </Button>
        </div>
      )}

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-1.5">
          {loading && (
            <div className="space-y-1 p-1">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-6" />
              ))}
            </div>
          )}

          {!loading && chapters.length === 0 && (
            <div className="flex flex-col items-center gap-1 px-3 py-8 text-center text-xs text-muted-foreground">
              <BookOpen className="size-4" />
              还没有章节
            </div>
          )}

          {volumes.map((volume) => {
            const items = grouped.get(volume.id) ?? [];
            return (
              <div key={volume.id} className="mb-1">
                <div className="flex items-center gap-1 px-1 py-1 text-[11px] font-medium text-muted-foreground">
                  <ChevronDown className="size-3 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{volume.title}</span>
                  <button
                    type="button"
                    className="shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
                    title="在本卷新建章节"
                    onClick={() => onCreateChapter(volume.id)}
                  >
                    <Plus className="size-3" />
                  </button>
                </div>
                <div className="ml-2 border-l pl-1">
                  {items.length === 0 && (
                    <div className="px-2 py-1 text-[11px] text-muted-foreground/60">（空）</div>
                  )}
                  {items.map((chapter) => (
                    <ChapterRow
                      key={chapter.id}
                      chapter={chapter}
                      active={chapter.id === activeChapterId}
                      onSelect={onSelect}
                      onDelete={onDeleteChapter}
                    />
                  ))}
                </div>
              </div>
            );
          })}

          {orphans.length > 0 && (
            <div className="mb-1">
              <div className="px-1 py-1 text-[11px] font-medium text-muted-foreground">未分卷</div>
              <div className="ml-2 border-l pl-1">
                {orphans.map((chapter) => (
                  <ChapterRow
                    key={chapter.id}
                    chapter={chapter}
                    active={chapter.id === activeChapterId}
                    onSelect={onSelect}
                    onDelete={onDeleteChapter}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}