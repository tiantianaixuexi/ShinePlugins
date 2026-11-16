import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateProject } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";
import type { Project } from "@/types/api";

interface ProjectEditDialogProps {
  project: Project;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProjectEditDialog({ project, open, onOpenChange }: ProjectEditDialogProps) {
  const updateProject = useUpdateProject(project.id);
  const [form, setForm] = useState({
    name: project.name,
    synopsis: project.synopsis,
    writing_style: project.writing_style,
    target_reader: project.target_reader,
    author: project.author,
    target_word_count: String(project.target_word_count || ""),
    target_chapter_count: String(project.target_chapter_count || ""),
  });

  useEffect(() => {
    if (!open) return;
    setForm({
      name: project.name,
      synopsis: project.synopsis,
      writing_style: project.writing_style,
      target_reader: project.target_reader,
      author: project.author,
      target_word_count: String(project.target_word_count || ""),
      target_chapter_count: String(project.target_chapter_count || ""),
    });
  }, [open, project]);

  const save = async () => {
    try {
      await updateProject.mutateAsync({
        name: form.name.trim(),
        synopsis: form.synopsis,
        writing_style: form.writing_style,
        target_reader: form.target_reader,
        author: form.author,
        target_word_count: form.target_word_count ? Number(form.target_word_count) : 0,
        target_chapter_count: form.target_chapter_count ? Number(form.target_chapter_count) : 0,
        row_version: project.row_version,
      });
      toast.success("项目设置已保存");
      onOpenChange(false);
    } catch (error) {
      toast.error("保存失败", { description: errorMessage(error) });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>编辑项目设置</DialogTitle>
          <DialogDescription>
            修改后立即生效，项目目录与数据库不受影响。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-2">
            <Label htmlFor="edit-name">小说名称</Label>
            <Input
              id="edit-name"
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-synopsis">小说简介</Label>
            <Textarea
              id="edit-synopsis"
              className="min-h-20"
              value={form.synopsis}
              onChange={(event) => setForm((prev) => ({ ...prev, synopsis: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-style">写作风格</Label>
            <Textarea
              id="edit-style"
              className="min-h-16"
              placeholder="例如：冷峻克制的硬科幻，重逻辑推演"
              value={form.writing_style}
              onChange={(event) => setForm((prev) => ({ ...prev, writing_style: event.target.value }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="edit-words">目标字数</Label>
              <Input
                id="edit-words"
                inputMode="numeric"
                value={form.target_word_count}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    target_word_count: event.target.value.replace(/[^\d]/g, ""),
                  }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-chapters">目标章节</Label>
              <Input
                id="edit-chapters"
                inputMode="numeric"
                value={form.target_chapter_count}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    target_chapter_count: event.target.value.replace(/[^\d]/g, ""),
                  }))
                }
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="edit-reader">目标读者</Label>
              <Input
                id="edit-reader"
                value={form.target_reader}
                onChange={(event) => setForm((prev) => ({ ...prev, target_reader: event.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-author">作者署名</Label>
              <Input
                id="edit-author"
                value={form.author}
                onChange={(event) => setForm((prev) => ({ ...prev, author: event.target.value }))}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={() => void save()} disabled={updateProject.isPending || !form.name.trim()}>
            {updateProject.isPending && <Loader2 className="size-4 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}