import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names and de-duplicate Tailwind conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format an integer with thousands separators, falling back to a dash. */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("zh-CN").format(value);
}

/** Compact notation for dashboard counters (12.4 万). */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 30 * day) return `${Math.floor(diff / day)} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

/** Rough token estimate used before the real tokenizer is wired up. */
export function estimateTokens(text: string): number {
  if (!text) return 0;
  // CJK characters are roughly one token each; Latin averages ~4 chars/token.
  let cjk = 0;
  for (const char of text) {
    if (/[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]/.test(char)) cjk += 1;
  }
  const rest = text.length - cjk;
  return Math.ceil(cjk + rest / 4);
}

const CJK_RE = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]/g;
const LATIN_RE = /[A-Za-z0-9]+/g;

/**
 * Mirror of the backend's `count_words`: each CJK character is one word and
 * each Latin/number run is one word. Keeping both in sync makes the live
 * counter agree with what gets stored.
 */
export function countWords(text: string): number {
  if (!text) return 0;
  const cjk = text.match(CJK_RE)?.length ?? 0;
  const latin = text.replace(CJK_RE, " ").match(LATIN_RE)?.length ?? 0;
  return cjk + latin;
}

export function readingMinutes(words: number, charsPerMinute = 400): number {
  if (words <= 0) return 0;
  return Math.max(1, Math.round(words / charsPerMinute));
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function percent(value: number, total: number): number {
  if (!total) return 0;
  return clamp(Math.round((value / total) * 100), 0, 100);
}

export function classNames(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}