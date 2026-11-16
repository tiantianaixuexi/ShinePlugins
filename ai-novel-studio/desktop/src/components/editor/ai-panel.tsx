import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowDownToLine,
  Check,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
  Square,
  TriangleAlert,
  Wand2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { streamAI } from "@/lib/ai";
import type { ApplyMode } from "@/lib/text-edit";
import { cn, countWords, formatNumber } from "@/lib/utils";
import type { AIOperation, AIResult } from "@/types/api";

export type { ApplyMode };

type Phase = "idle" | "streaming" | "done" | "error";

interface AIOperationDef {
  id: AIOperation;
  label: string;
  hint: string;
  /** Whether the result is meant to be written into the manuscript. */
  applies: boolean;
  needsSelection: boolean;
}

const OPERATIONS: AIOperationDef[] = [
  { id: "continue", label: "续写", hint: "从正文结尾自然接续", applies: true, needsSelection: false },
  { id: "expand", label: "扩写", hint: "选中段落补充细节", applies: true, needsSelection: true },
  { id: "rewrite", label: "改写", hint: "按指令重组内容", applies: true, needsSelection: true },
  { id: "polish", label: "润色", hint: "提升语言质量", applies: true, needsSelection: true },
  { id: "review", label: "审稿", hint: "检查连贯性", applies: false, needsSelection: false },
];

const INSTRUCTION_PLACEHOLDER: Record<AIOperation, string> = {
  continue: "例如：节奏再快一点，多用对白，150 字左右",
  expand: "例如：补充环境细节与心理活动",
  rewrite: "例如：换成第一人称，增强冲突",
  polish: "例如：让语言更凝练，去掉多余形容词",
  review: "例如：重点看时间线与人物已知信息",
  outline: "",
  write: "",
};

interface AIPanelProps {
  projectId: string;
  chapterId: string;
  content: string;
  selection: string;
  onApply: (text: string, mode: ApplyMode) => void;
  onClose: () => void;
}

export function AIPanel({
  projectId,
  chapterId,
  content,
  selection,
  onApply,
  onClose,
}: AIPanelProps) {
  const [operation, setOperation] = useState<AIOperation>("continue");
  const [instruction, setInstruction] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [output, setOutput] = useState("");
  const [result, setResult] = useState<AIResult | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);

  const controller = useRef<AbortController | null>(null);
  const def = OPERATIONS.find((item) => item.id === operation) ?? OPERATIONS[0];

  const stop = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setPhase((current) => (current === "streaming" ? "done" : current));
  }, []);

  const run = useCallback(async () => {
    if (phase === "streaming") return;
    if (def.needsSelection && !selection.trim()) {
      toast.error("请先在正文中选中要处理的段落");
      return;
    }

    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;

    setPhase("streaming");
    setOutput("");
    setResult(null);
    setError(null);

    await streamAI(
      operation,
      {
        project_id: projectId,
        chapter_id: chapterId,
        content,
        selection,
        instruction,
      },
      {
        onDelta: (text) => {
          if (!abort.signal.aborted) setOutput((previous) => previous + text);
        },
        onDone: (payload) => {
          if (abort.signal.aborted) return;
          setResult(payload);
          setPhase("done");
        },
        onError: (payload) => {
          if (abort.signal.aborted) return;
          setError(payload);
          setPhase("error");
        },
      },
      abort.signal,
    );
  }, [chapterId, content, def.needsSelection, instruction, operation, phase, projectId, selection]);

  const apply = (mode: ApplyMode) => {
    if (!output.trim()) return;
    onApply(output, mode);
    toast.success("已写入正文");
    setOutput("");
    setResult(null);
    setPhase("idle");
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(output);
      toast.success("已复制");
    } catch {
      toast.error("复制失败");
    }
  };

  const busy = phase === "streaming";
  const words = countWords(output);

  return (
    <div className="flex h-full min-h-0 w-80 shrink-0 flex-col border-l bg-card/40">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Sparkles className="size-4 text-primary" />
        <span className="text-sm font-medium">AI 助手</span>
        <Badge variant="outline" className="text-[10px]">
          {def.label}
        </Badge>
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto"
          title="关闭 AI 面板"
          onClick={onClose}
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="space-y-3 border-b p-3">
        <div className="flex flex-wrap gap-1">
          {OPERATIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={busy}
              onClick={() => {
                setOperation(item.id);
                setPhase("idle");
                setOutput("");
                setResult(null);
                setError(null);
              }}
              className={cn(
                "rounded-md border px-2 py-1 text-xs transition-colors disabled:opacity-50",
                item.id === operation
                  ? "border-primary/40 bg-primary/15 font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <p className="text-[11px] text-muted-foreground">{def.hint}</p>

        <Textarea
          value={instruction}
          disabled={busy}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder={INSTRUCTION_PLACEHOLDER[operation]}
          className="min-h-16 resize-none text-xs"
        />

        <div className="flex items-center gap-2">
          {busy ? (
            <Button size="sm" variant="outline" className="flex-1" onClick={stop}>
              <Square className="size-3.5" />
              停止
            </Button>
          ) : (
            <Button
              size="sm"
              className="flex-1"
              disabled={def.needsSelection && !selection.trim()}
              onClick={() => void run()}
            >
              <Wand2 className="size-4" />
              {phase === "idle" ? "生成" : "重新生成"}
            </Button>
          )}
        </div>

        {def.needsSelection && (
          <p
            className={cn(
              "text-[11px]",
              selection.trim() ? "text-muted-foreground" : "text-amber-600 dark:text-amber-400",
            )}
          >
            {selection.trim()
              ? `已选中 ${countWords(selection)} 字`
              : "未选中文本：请先在正文里选中要处理的段落"}
          </p>
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">
          {phase === "idle" && !output && (
            <p className="py-8 text-center text-xs text-muted-foreground">
              选择操作后点「生成」。生成结果不会直接改动正文，由你决定是否采用。
            </p>
          )}

          {busy && !output && (
            <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              正在请求模型…
            </div>
          )}

          {phase === "error" && error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-destructive">
                <TriangleAlert className="size-3.5" />
                生成失败
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {error.message}
              </p>
              <p className="mt-1 font-mono text-[10px] text-muted-foreground/70">{error.code}</p>
            </div>
          )}

          {output && (
            <div className="whitespace-pre-wrap rounded-lg border bg-background p-3 text-xs leading-relaxed">
              {output}
              {busy && <span className="ml-0.5 inline-block animate-pulse">▍</span>}
            </div>
          )}

          {result && !busy && (
            <p className="mt-2 text-[10px] text-muted-foreground">
              {result.model} · 输入 {formatNumber(result.input_tokens)} · 输出{" "}
              {formatNumber(result.output_tokens)} token
              {result.cost > 0 ? ` · ¥${result.cost.toFixed(4)}` : ""}
            </p>
          )}

          {output && !busy && (
            <p className="mt-1 text-[10px] text-muted-foreground">{words} 字</p>
          )}
        </div>
      </ScrollArea>

      {output && !busy && (
        <div className="flex flex-wrap gap-1 border-t p-2">
          <Button size="sm" variant="ghost" onClick={() => void copy()} title="复制">
            <Copy className="size-3.5" />
          </Button>
          {def.applies ? (
            <>
              {selection.trim() && (
                <Button size="sm" variant="outline" onClick={() => apply("replace-selection")}>
                  <Check className="size-3.5" />
                  替换选中
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => apply("append")}>
                <ArrowDownToLine className="size-3.5" />
                插入末尾
              </Button>
              <Button size="sm" variant="outline" onClick={() => apply("replace-all")}>
                <RefreshCw className="size-3.5" />
                替换全文
              </Button>
            </>
          ) : (
            <span className="px-1 py-1 text-[10px] text-muted-foreground">
              审稿结果仅供参考，不会写入正文
            </span>
          )}
        </div>
      )}
    </div>
  );
}