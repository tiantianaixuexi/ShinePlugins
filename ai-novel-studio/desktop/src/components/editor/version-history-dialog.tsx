import { useState } from "react";
import { toast } from "sonner";
import { History, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChapterVersions, useRestoreChapter, useSnapshotChapter } from "@/hooks/use-novel";
import { errorMessage } from "@/lib/api";
import { formatNumber, formatRelativeTime } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  user: "写作",
  ai: "AI",
  import: "导入",
  restore: "恢复",
};

interface VersionHistoryDialogProps {
  projectId: string;
  chapterId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRestored?: () => void;
}

export function VersionHistoryDialog({
  projectId,
  chapterId,
  open,
  onOpenChange,
  onRestored,
}: VersionHistoryDialogProps) {
  const versions = useChapterVersions(projectId, open ? chapterId : null);
  const snapshot = useSnapshotChapter(projectId, chapterId);
  const restore = useRestoreChapter(projectId, chapterId);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const handleSnapshot = async () => {
    try {
      await snapshot.mutateAsync();
      toast.success("已保存当前版本");
    } catch (error) {
      toast.error("保存版本失败", { description: errorMessage(error) });
    }
  };

  const handleRestore = async (versionId: string) => {
    setRestoringId(versionId);
    try {
      await restore.mutateAsync(versionId);
      toast.success("已恢复到该版本", { description: "当前内容已另存为一个版本。" });
      onRestored?.();
      onOpenChange(false);
    } catch (error) {
      toast.error("恢复失败", { description: errorMessage(error) });
    } finally {
      setRestoringId(null);
    }
  };

  const rows = versions.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="size-4" />
            历史版本
          </DialogTitle>
          <DialogDescription>
            自动保存每 5 分钟最多记录一次，手动快照始终保存。恢复前会先为当前内容存档。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[55vh] pr-2">
          {versions.isPending && (
            <div className="space-y-2 py-1">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-12" />
              ))}
            </div>
          )}

          {versions.isError && (
            <p className="py-6 text-center text-sm text-destructive">
              {errorMessage(versions.error)}
            </p>
          )}

          {!versions.isPending && !versions.isError && rows.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">还没有历史版本。</p>
          )}

          <ul className="space-y-2 py-1">
            {rows.map((version) => (
              <li
                key={version.id}
                className="flex items-center gap-3 rounded-lg border px-3 py-2"
              >
                <div className="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-[11px] font-semibold tabular-nums">
                  v{version.version_no}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-sm">
                    <span className="truncate font-medium">{version.title || "未命名章节"}</span>
                    <span className="shrink-0 rounded bg-muted px-1 text-[10px] text-muted-foreground">
                      {SOURCE_LABEL[version.source] ?? version.source}
                    </span>
                  </div>
                  <div className="truncate text-[11px] text-muted-foreground">
                    {formatNumber(version.word_count)} 字 · {formatRelativeTime(version.created_at)}
                    {version.note ? ` · ${version.note}` : ""}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={restore.isPending && restoringId === version.id}
                  onClick={() => void handleRestore(version.id)}
                >
                  {restore.isPending && restoringId === version.id ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RotateCcw className="size-4" />
                  )}
                  恢复
                </Button>
              </li>
            ))}
          </ul>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          <Button onClick={() => void handleSnapshot()} disabled={snapshot.isPending}>
            {snapshot.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <History className="size-4" />
            )}
            保存当前版本
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}