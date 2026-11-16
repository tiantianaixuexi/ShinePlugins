import { useEffect, useMemo, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateProject } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";
import type { ProjectCreate } from "@/types/api";

export const NOVEL_TYPES = [
  "玄幻",
  "都市",
  "科幻",
  "悬疑",
  "言情",
  "历史",
  "武侠",
  "游戏",
  "现实",
  "其他",
] as const;

interface FormState {
  name: string;
  novel_type: string;
  synopsis: string;
  target_word_count: string;
  target_chapter_count: string;
  writing_style: string;
  target_reader: string;
  language: string;
  author: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  novel_type: "玄幻",
  synopsis: "",
  target_word_count: "",
  target_chapter_count: "",
  writing_style: "",
  target_reader: "",
  language: "zh-CN",
  author: "",
};

function toInt(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

interface ProjectFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (id: string) => void;
}

export function ProjectFormDialog({ open, onOpenChange, onCreated }: ProjectFormDialogProps) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const createProject = useCreateProject();

  useEffect(() => {
    if (open) setForm(EMPTY_FORM);
  }, [open]);

  const canSubmit = useMemo(() => form.name.trim().length > 0, [form.name]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async () => {
    if (!canSubmit) return;
    const payload: ProjectCreate = {
      name: form.name.trim(),
      novel_type: form.novel_type,
      synopsis: form.synopsis,
      target_word_count: toInt(form.target_word_count) ?? 0,
      target_chapter_count: toInt(form.target_chapter_count) ?? 0,
      writing_style: form.writing_style,
      target_reader: form.target_reader,
      language: form.language || "zh-CN",
      author: form.author,
    };
    try {
      const project = await createProject.mutateAsync(payload);
      toast.success(`已创建《${project.name}》`);
      onOpenChange(false);
      onCreated?.(project.id);
    } catch (error) {
      toast.error("创建项目失败", { description: errorMessage(error) });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>新建小说项目</DialogTitle>
          <DialogDescription>
            创建后会在本地生成独立的项目目录与数据库，可随时备份或迁移。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-2">
            <Label htmlFor="project-name">
              小说名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="project-name"
              autoFocus
              placeholder="例如：星海纪元"
              value={form.name}
              onChange={(event) => set("name", event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void handleSubmit();
                }
              }}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>小说类型</Label>
              <Select value={form.novel_type} onValueChange={(value) => set("novel_type", value)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择类型" />
                </SelectTrigger>
                <SelectContent>
                  {NOVEL_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="project-language">创作语言</Label>
              <Select value={form.language} onValueChange={(value) => set("language", value)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择语言" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="zh-CN">简体中文</SelectItem>
                  <SelectItem value="zh-TW">繁体中文</SelectItem>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="ja">日本語</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="project-synopsis">小说简介</Label>
            <Textarea
              id="project-synopsis"
              placeholder="一句话概括故事的核心设定、主角与目标…"
              className="min-h-20 resize-y"
              value={form.synopsis}
              onChange={(event) => set("synopsis", event.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="project-words">目标字数</Label>
              <Input
                id="project-words"
                inputMode="numeric"
                placeholder="例如 1000000"
                value={form.target_word_count}
                onChange={(event) => set("target_word_count", event.target.value.replace(/[^\d]/g, ""))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="project-chapters">目标章节</Label>
              <Input
                id="project-chapters"
                inputMode="numeric"
                placeholder="例如 500"
                value={form.target_chapter_count}
                onChange={(event) => set("target_chapter_count", event.target.value.replace(/[^\d]/g, ""))}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="project-style">写作风格</Label>
            <Textarea
              id="project-style"
              placeholder="例如：冷峻克制的硬科幻，重逻辑推演，少形容词"
              className="min-h-16"
              value={form.writing_style}
              onChange={(event) => set("writing_style", event.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="project-reader">目标读者</Label>
              <Input
                id="project-reader"
                placeholder="例如：18-35 岁男性向读者"
                value={form.target_reader}
                onChange={(event) => set("target_reader", event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="project-author">作者署名</Label>
              <Input
                id="project-author"
                placeholder="笔名"
                value={form.author}
                onChange={(event) => set("author", event.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit || createProject.isPending}>
            {createProject.isPending && <Loader2 className="size-4 animate-spin" />}
            创建项目
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}