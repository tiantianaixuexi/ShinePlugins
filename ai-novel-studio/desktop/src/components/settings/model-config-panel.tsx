import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Check, Cpu, KeyRound, Loader2, Plus, Star, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import type { ModelConfig, ModelConfigCreate } from "@/types/api";

/**
 * Only used to render a human label for rows created by older versions.
 * New rows are created through the generic OpenAI-compatible path.
 */
const PROVIDER_LABELS: Record<string, string> = {
  openai_compatible: "OpenAI 兼容",
  openai: "OpenAI",
  deepseek: "DeepSeek",
  minimax: "MiniMax",
  ollama: "Ollama",
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
  custom: "自定义",
};

const EMPTY: ModelConfigCreate = {
  name: "",
  provider: "openai_compatible",
  base_url: "",
  model_name: "",
  api_key: "",
  context_window: 128000,
  max_tokens: 4096,
  temperature: 0.8,
  notes: "",
};

const BASE_URL_EXAMPLES = [
  { label: "MiniMax", url: "https://api.minimax.io/v1" },
  { label: "DeepSeek", url: "https://api.deepseek.com/v1" },
  { label: "Ollama 本地", url: "http://127.0.0.1:11434/v1" },
];

function ModelRow({
  model,
  onDelete,
  onDefault,
  busy,
}: {
  model: ModelConfig;
  onDelete: () => void;
  onDefault: () => void;
  busy: boolean;
}) {
  return (
    <li className="flex items-start gap-3 rounded-lg border px-3 py-2.5">
      <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-muted">
        <Cpu className="size-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="truncate text-sm font-medium">{model.name}</span>
          {model.is_default && (
            <Badge variant="success" className="gap-1">
              <Star className="size-2.5" />
              默认
            </Badge>
          )}
          <Badge variant={model.has_api_key ? "outline" : "warning"} className="gap-1">
            <KeyRound className="size-2.5" />
            {model.has_api_key ? "已配置密钥" : "缺少密钥"}
          </Badge>
          {!model.is_active && <Badge variant="muted">已停用</Badge>}
        </div>
        <div className="truncate text-[11px] text-muted-foreground">
          {PROVIDER_LABELS[model.provider] ?? model.provider} · {model.model_name}
          {model.base_url ? ` · ${model.base_url}` : ""}
        </div>
        <div className="text-[11px] text-muted-foreground">
          上下文 {formatNumber(model.context_window)} · 输出 {formatNumber(model.max_output_tokens)} ·
          temperature {model.temperature}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {!model.is_default && (
          <Button variant="ghost" size="icon-sm" title="设为默认" disabled={busy} onClick={onDefault}>
            <Check className="size-4" />
          </Button>
        )}
        <Button variant="ghost" size="icon-sm" title="删除" disabled={busy} onClick={onDelete}>
          <Trash2 className="size-4 text-muted-foreground hover:text-destructive" />
        </Button>
      </div>
    </li>
  );
}

export function ModelConfigPanel() {
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: ["model-configs"], queryFn: () => api.modelConfigs.list() });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ModelConfigCreate>(EMPTY);
  const [saving, setSaving] = useState(false);

  const create = useMutation({
    mutationFn: (payload: ModelConfigCreate) => api.modelConfigs.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-configs"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.modelConfigs.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-configs"] });
    },
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => api.modelConfigs.setDefault(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["model-configs"] });
    },
  });

  const canSubmit = useMemo(
    () =>
      form.name.trim().length > 0 &&
      form.model_name.trim().length > 0 &&
      (form.base_url ?? "").trim().length > 0,
    [form],
  );

  const submit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      await create.mutateAsync({
        ...form,
        name: form.name.trim(),
        base_url: (form.base_url ?? "").trim(),
        model_name: form.model_name.trim(),
        api_key: form.api_key?.trim() ? form.api_key.trim() : null,
      });
      toast.success("模型配置已保存");
      setOpen(false);
      setForm(EMPTY);
    } catch (error) {
      toast.error("保存失败", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    try {
      await remove.mutateAsync(id);
      toast.success(`已删除 ${name}`);
    } catch (error) {
      toast.error("删除失败", { description: errorMessage(error) });
    }
  };

  const handleDefault = async (id: string) => {
    try {
      await setDefault.mutateAsync(id);
      toast.success("已设为默认模型");
    } catch (error) {
      toast.error("设置失败", { description: errorMessage(error) });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">模型配置</h3>
          <p className="text-xs text-muted-foreground">
            任何 OpenAI 兼容端点都可以直接填 URL、Key 和模型名；密钥经 Windows DPAPI
            加密后写入本地，不会出现在数据库或响应里。
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          添加模型
        </Button>
      </div>

      {models.isPending && <Skeleton className="h-24" />}

      {models.isError && (
        <p className="rounded-lg border border-destructive/40 px-3 py-2 text-xs text-destructive">
          {errorMessage(models.error)}
        </p>
      )}

      {!models.isPending && !models.isError && (models.data?.length ?? 0) === 0 && (
        <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
          还没有配置模型。添加一个 OpenAI 兼容端点即可开始生成。
        </p>
      )}

      <ul className="space-y-2">
        {models.data?.map((model) => (
          <ModelRow
            key={model.id}
            model={model}
            busy={remove.isPending || setDefault.isPending}
            onDelete={() => void handleDelete(model.id, model.name)}
            onDefault={() => void handleDefault(model.id)}
          />
        ))}
      </ul>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>添加模型配置</DialogTitle>
            <DialogDescription>
              填写任意 OpenAI 兼容服务的 Base URL、模型名与密钥即可，无需为每家服务商单独适配。
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-1">
            <div className="grid gap-1.5">
              <Label htmlFor="model-name">显示名称</Label>
              <Input
                id="model-name"
                autoFocus
                placeholder="例如：MiniMax 写作模型"
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="model-url">Base URL</Label>
              <Input
                id="model-url"
                placeholder="https://api.minimax.io/v1"
                value={form.base_url ?? ""}
                onChange={(event) => setForm((prev) => ({ ...prev, base_url: event.target.value }))}
              />
              <div className="flex flex-wrap gap-1">
                {BASE_URL_EXAMPLES.map((example) => (
                  <button
                    key={example.url}
                    type="button"
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        base_url: example.url,
                        provider:
                          example.label === "MiniMax"
                            ? "minimax"
                            : example.label === "DeepSeek"
                              ? "deepseek"
                              : example.label === "Ollama 本地"
                                ? "ollama"
                                : prev.provider,
                      }))
                    }
                    className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {example.label} · {example.url}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="model-id">模型名称</Label>
              <Input
                id="model-id"
                placeholder="例如：MiniMax-M2"
                value={form.model_name}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, model_name: event.target.value }))
                }
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="model-key">API Key</Label>
              <Input
                id="model-key"
                type="password"
                autoComplete="off"
                placeholder="留空表示暂不填写，可稍后补充"
                value={form.api_key ?? ""}
                onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))}
              />
              <p className="text-[11px] text-muted-foreground">
                密钥只写入本机加密存储（Windows 为 DPAPI），不会出现在数据库、日志或响应中。
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="model-ctx">上下文窗口</Label>
                <Input
                  id="model-ctx"
                  inputMode="numeric"
                  value={String(form.context_window ?? 0)}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      context_window: Number(event.target.value.replace(/[^\d]/g, "")) || 0,
                    }))
                  }
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="model-out">最大输出</Label>
                <Input
                  id="model-out"
                  inputMode="numeric"
                  value={String(form.max_tokens ?? 0)}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      max_tokens: Number(event.target.value.replace(/[^\d]/g, "")) || 0,
                    }))
                  }
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="model-temp">Temperature</Label>
                <Input
                  id="model-temp"
                  inputMode="decimal"
                  value={String(form.temperature ?? 0)}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      temperature: Number(event.target.value.replace(/[^\d.]/g, "")) || 0,
                    }))
                  }
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button onClick={() => void submit()} disabled={!canSubmit || saving}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}