/**
 * Pure text-edit operations shared by the AI panel and the editor.
 *
 * Kept free of React so the behaviour can be unit-tested without a DOM.
 */

export type ApplyMode = "replace-selection" | "append" | "replace-all";

export interface TextEditResult {
  content: string;
  /** Where the caret should land after the edit. */
  caret: number;
}

export interface TextRange {
  start: number;
  end: number;
}

/**
 * Insert *text* into *content*.
 *
 * - ``replace-all`` swaps the whole manuscript;
 * - ``replace-selection`` swaps the selected range, and falls back to appending
 *   when the selection is empty or collapsed;
 * - ``append`` adds the text as a new paragraph at the end.
 */
export function applyText(
  content: string,
  range: TextRange | null,
  text: string,
  mode: ApplyMode,
): TextEditResult {
  if (mode === "replace-all") {
    return { content: text, caret: text.length };
  }

  const start = Math.min(Math.max(range?.start ?? content.length, 0), content.length);
  const end = Math.min(Math.max(range?.end ?? content.length, start), content.length);

  if (mode === "replace-selection" && end > start) {
    return {
      content: content.slice(0, start) + text + content.slice(end),
      caret: start + text.length,
    };
  }

  const base = content.replace(/\s+$/, "");
  const next = base.length ? `${base}\n\n${text}` : text;
  return { content: next, caret: next.length };
}