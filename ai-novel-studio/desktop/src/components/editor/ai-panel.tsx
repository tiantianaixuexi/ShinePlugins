import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowDownToLine,
  Check,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
  Square,
  Trash2,
  TriangleAlert,
  Wand2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { applyStreamOutcome, streamAI, streamOutline, streamSummary } from "@/lib/ai";
import type { ApplyMode } from "@/lib/text-edit";
import { cn, countWords, formatNumber } from "@/lib/utils";
import type {
  AIOperation,
  AIResult,
  OutlineStreamResult,
  SummaryStreamResult,
} from "@/types/api";

export type { ApplyMode };

type Phase = "idle" | "streaming" | "done" | "error";

/** Panel actions: the writing operations plus the two structured generators. */
type ActionId = AIOperation | "gen-outline" | "gen-summary";

interface AIOperationDef {
  id: ActionId;
  label: string;
  hint: string;
  /** Whether the result is meant to be written into the manuscript. */
  applies: boolean;
  needsSelection: boolean;
  /**
   * Set for the structured endpoints (`/ai/summary|outline/{id}/stream`).
   * They persist their own row, so they never get an 「应用」 button.
   */
  structured?: "summary" | "outline";
}

const OPERATIONS: AIOperationDef[] = [
  { id: "continue", label: "续写", hint: "从正文结尾自然接续", applies: true, needsSelection: false },
  { id: "expand", label: "扩写", hint: "选中段落补充细节", applies: true, needsSelection: true },
  { id: "rewrite", label: "改写", hint: "按指令重组内容", applies: true, needsSelection: true },
  { id: "polish", label: "润色", hint: "提升语言质量", applies: true, needsSelection: true },
  { id: "review", label: "审稿", hint: "检查连贯性", applies: false, needsSelection: false },
  {
    id: "gen-outline",
    label: "生成大纲",
    hint: "为本章生成结构化大纲并保存到项目（最慢的一次调用）",
    applies: false,
    needsSelection: false,
    structured: "outline",
  },
  {
    id: "gen-summary",
    label: "生成摘要",
    hint: "把本章压缩成一段摘要，作为长篇记忆写入项目",
    applies: false,
    needsSelection: false,
    structured: "summary",
  },
];

const INSTRUCTION_PLACEHOLDER: Partial<Record<ActionId, string>> = {
  continue: "例如：节奏再快一点，多用对白，150 字左右",
  expand: "例如：补充环境细节与心理活动",
  rewrite: "例如：换成第一人称，增强冲突",
  polish: "例如：让语言更凝练，去掉多余形容词",
  review: "例如：重点看时间线与人物已知信息",
  "gen-outline": "例如：这一章节奏放慢，结尾留钩子",
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
  const [operation, setOperation] = useState<ActionId>("continue");
  const [instruction, setInstruction] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [output, setOutput] = useState("");
  const [result, setResult] = useState<AIResult | null>(null);
  const [summary, setSummary] = useState<SummaryStreamResult | null>(null);
  const [outline, setOutline] = useState<OutlineStreamResult | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [firstCharMs, setFirstCharMs] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const controller = useRef<AbortController | null>(null);
  const startedAt = useRef(0);
  const firstCharAt = useRef<number | null>(null);
  const def = OPERATIONS.find((item) => item.id === operation) ?? OPERATIONS[0];

  // A ticking clock, so 「已用时」 keeps moving during a 100-second outline call.
  useEffect(() => {
    if (phase !== "streaming") return;
    const timer = window.setInterval(() => {
      setElapsedMs(performance.now() - startedAt.current);
    }, 100);
    return () => window.clearInterval(timer);
  }, [phase]);

  const stop = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setElapsedMs(performance.now() - startedAt.current);
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

    startedAt.current = performance.now();
    firstCharAt.current = null;
    setFirstCharMs(null);
    setElapsedMs(0);
    setPhase("streaming");
    setOutput("");
    setResult(null);
    setSummary(null);
    setOutline(null);
    setError(null);

    const appendDelta = (text: string) => {
      if (abort.signal.aborted) return;
      if (firstCharAt.current === null) {
        firstCharAt.current = performance.now();
        setFirstCharMs(firstCharAt.current - startedAt.current);
      }
      setOutput((previous) => applyStreamOutcome(previous, { kind: "delta", text }));
    };

    /** The backend restarted the reply (JSON repair retry): drop the buffer. */
    const dropDeltas = () => {
      if (abort.signal.aborted) return;
      setOutput((previous) => applyStreamOutcome(previous, { kind: "reset" }));
    };

    const settle = () => {
      setElapsedMs(performance.now() - startedAt.current);
      setPhase("done");
    };

    const onError = (payload: { code: string; message: string }) => {
      if (abort.signal.aborted) return;
      setElapsedMs(performance.now() - startedAt.current);
      setError(payload);
      setPhase("error");
    };

    // The first click honours the server-side cache; 「重新生成」 forces a call.
    const force = phase !== "idle";

    if (def.structured === "summary") {
      await streamSummary(
        chapterId,
        { project_id: projectId, force },
        {
          onDelta: appendDelta,
          onReset: dropDeltas,
          onDone: (payload) => {
            if (abort.signal.aborted) return;
            setSummary(payload);
            settle();
          },
          onError,
        },
        abort.signal,
      );
      return;
    }

    if (def.structured === "outline") {
      await streamOutline(
        chapterId,
        { project_id: projectId, force, instruction },
        {
          onDelta: appendDelta,
          onReset: dropDeltas,
          onDone: (payload) => {
            if (abort.signal.aborted) return;
            setOutline(payload);
            settle();
          },
          onError,
        },
        abort.signal,
      );
      return;
    }

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
        onDelta: appendDelta,
        onReset: dropDeltas,
        onDone: (payload) => {
          if (abort.signal.aborted) return;
          setResult(payload);
          settle();
        },
        onError,
      },
      abort.signal,
    );
  }, [chapterId, content, def, instruction, operation, phase, projectId, selection]);

  const apply = (mode: ApplyMode) => {
    if (!output.trim()) return;
    onApply(output, mode);
    toast.success("已写入正文");
    setOutput("");
    setResult(null);
    setPhase("idle");
  };

  /** 放弃本次生成结果：不动正文，只清空面板状态。 */
  const discard = useCallback((silent = false) => {
    controller.current?.abort();
    controller.current = null;
    setOutput("");
    setResult(null);
    setSummary(null);
    setOutline(null);
    setError(null);
    setPhase("idle");
    if (!silent) toast.success("已丢弃，正文未改动");
  }, []);

  const close = useCallback(() => {
    // 关面板前先丢弃，避免「关了才想起来没采纳」的沉默丢失。
    if (output.trim() || summary || outline) discard(true);
    onClose();
  }, [discard, onClose, outline, output, summary]);

  /** What 「复制」 puts on the clipboard: the text, or the structured answer. */
  const clipText = def.structured
    ? def.structured === "summary"
      ? (summary?.summary ?? output)
      : outline
        ? outlineToText(outline)
        : output
    : output;

  const copy = async () => {
    if (!clipText.trim()) return;
    try {
      await navigator.clipboard.writeText(clipText);
      toast.success("已复制");
    } catch {
      toast.error("复制失败");
    }
  };

  const busy = phase === "streaming";
  const words = countWords(output);
  // 结构化端点写入的是项目里的行，不写正文，所以没有「应用」按钮。
  const structuredUsage = def.structured === "summary" ? summary?.usage : outline?.usage;
  // 原文在生成期间始终可见；结构化操作只在降级或失败时保留原文。
  const showRaw = busy || !def.structured || Boolean(outline?.degraded) || Boolean(summary && !summary.summary);

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
          onClick={close}
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
                setSummary(null);
                setOutline(null);
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

        {/* 生成摘要没有可选指令，就不摆一个不起作用的输入框。 */}
        {INSTRUCTION_PLACEHOLDER[operation] !== undefined && (
          <Textarea
            value={instruction}
            disabled={busy}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder={INSTRUCTION_PLACEHOLDER[operation]}
            className="min-h-16 resize-none text-xs"
          />
        )}

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

          {/* 生成过程可见性：模型吐了多久、首字多久、已经收到多少。 */}
          {busy && (
            <p className="mb-1 font-mono text-[10px] text-muted-foreground">
              已接收 {countWords(output)} 字 · 首字{" "}
              {firstCharMs === null ? "—" : `${(firstCharMs / 1000).toFixed(1)}s`} · 已用时{" "}
              {(elapsedMs / 1000).toFixed(1)}s
            </p>
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

          {output && showRaw && (
            <div
              className={cn(
                "rounded-lg border bg-background p-3 text-xs leading-relaxed",
                def.structured
                  ? "max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px]"
                  : "whitespace-pre-wrap",
              )}
            >
              {output}
              {busy && <span className="ml-0.5 inline-block animate-pulse">▍</span>}
            </div>
          )}

          {!busy && summary && (
            <div className="mt-2 space-y-2 rounded-lg border bg-background p-3">
              <div className="text-[11px] font-medium text-muted-foreground">章节摘要</div>
              {summary.summary ? (
                <p className="whitespace-pre-wrap text-xs leading-relaxed">{summary.summary}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {summary.skipped === "empty"
                    ? "本章正文为空，没有可摘要的内容。"
                    : "模型只返回了原文，没有结构化摘要。"}
                </p>
              )}
              {summary.cached && (
                <p className="text-[10px] text-muted-foreground">沿用已有摘要（未调用模型）</p>
              )}
            </div>
          )}

          {!busy && outline && (
            <div className="mt-2 space-y-2 rounded-lg border bg-background p-3">
              {outline.degraded && (
                <div className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] leading-relaxed text-amber-700 dark:text-amber-300">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                  <span>模型未返回结构化结果，已保留原文</span>
                </div>
              )}
              <div className="text-xs font-medium">{outline.title}</div>
              <StructuredField label="目标" value={outline.goal} />
              <StructuredField label="冲突" value={outline.conflict} />
              {outline.key_events.length > 0 && (
                <div className="text-xs leading-relaxed">
                  <span className="text-muted-foreground">关键事件：</span>
                  <ul className="mt-0.5 list-disc pl-4">
                    {outline.key_events.map((event) => (
                      <li key={event}>{event}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {result && !busy && (
            <p className="mt-2 text-[10px] text-muted-foreground">
              {result.model} · 输入 {formatNumber(result.input_tokens)} · 输出{" "}
              {formatNumber(result.output_tokens)} token
              {result.cost > 0 ? ` · ¥${result.cost.toFixed(4)}` : ""}
            </p>
          )}

          {structuredUsage && !busy && (
            <p className="mt-2 text-[10px] text-muted-foreground">
              输入 {formatNumber(structuredUsage.input_tokens)} · 输出{" "}
              {formatNumber(structuredUsage.output_tokens)} token
            </p>
          )}

          {output && !busy && !def.structured && (
            <p className="mt-1 text-[10px] text-muted-foreground">{words} 字</p>
          )}
        </div>
      </ScrollArea>

      {(output || summary || outline) && (
        <div className="flex flex-wrap gap-1 border-t p-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={!clipText.trim()}
            onClick={() => void copy()}
            title="复制"
          >
            <Copy className="size-3.5" />
          </Button>
          {!busy && def.structured && (
            <span className="px-1 py-1 text-[10px] text-muted-foreground">
              已保存到项目，不写入正文
            </span>
          )}
          {!busy &&
            !def.structured &&
            (def.applies ? (
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
            ))}
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto text-muted-foreground"
            disabled={!clipText.trim()}
            onClick={() => discard()}
            title="丢弃这次结果，正文不改动"
          >
            <Trash2 className="size-3.5" />
            丢弃
          </Button>
        </div>
      )}
    </div>
  );
}

/** One 「标签：值」 line of a structured result; empty values are skipped. */
function StructuredField({ label, value }: { label: string; value?: string }) {
  if (!value?.trim()) return null;
  return (
    <p className="whitespace-pre-wrap text-xs leading-relaxed">
      <span className="text-muted-foreground">{label}：</span>
      {value}
    </p>
  );
}

/** Flatten an outline into clipboard text (this operation never touches the正文). */
function outlineToText(outline: OutlineStreamResult): string {
  const lines = [outline.title];
  if (outline.goal) lines.push(`目标：${outline.goal}`);
  if (outline.conflict) lines.push(`冲突：${outline.conflict}`);
  if (outline.ending) lines.push(`结尾：${outline.ending}`);
  if (outline.key_events.length > 0) {
    lines.push("关键事件：", ...outline.key_events.map((event) => `- ${event}`));
  }
  return lines.join("\n");
}