/**
 * When to refresh a chapter's L1 summary (「前情提要」) without being asked.
 *
 * Summarising costs a model call, so it must never run on every keystroke: the
 * editor's autosave fires ~1200 ms after typing stops, and hanging a paid request
 * off that would burn tokens continuously. The trigger is instead **leaving the
 * chapter** — switching to another chapter, which is exactly the moment the
 * author stops working on this one and the text is as settled as it gets.
 *
 * Two guards keep that cheap:
 *
 * 1. the body must not be blank (nothing to distil);
 * 2. the same `chapterId` + body pair is only ever sent once per session, so
 *    flipping back and forth between two chapters does not re-trigger.
 *
 * The backend has its own content-fingerprint cache, so this is the cheap client
 * side of the same idea — but it is kept here as a pure function so it is
 * testable without mounting the editor.
 */

/** Cheap, synchronous fingerprint of a chapter body (djb2 over code units). */
export function contentFingerprint(content: string): string {
  const text = (content ?? "").trim();
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(index)) | 0;
  }
  // Length is mixed in so two different texts cannot collide via a shifted-out
  // high bit, and a trimmed body of only whitespace differences stays stable.
  return `${(hash >>> 0).toString(36)}-${text.length}`;
}

/** Identity of "this chapter, as the author left it". */
export function summaryTriggerKey(chapterId: string, content: string): string {
  return `${chapterId}:${contentFingerprint(content)}`;
}

export interface SummaryTriggerLog {
  /** True the first time this `(chapter, content)` pair is offered, false after. */
  claim(chapterId: string, content: string): boolean;
  /** How many distinct pairs have been triggered this session. */
  readonly size: number;
}

/**
 * Session-scoped memory of already-triggered summaries.
 *
 * Hold one per editor page (a `useRef`) so it survives the component remount
 * that happens on every chapter switch.
 */
export function createSummaryTriggerLog(): SummaryTriggerLog {
  const seen = new Set<string>();
  return {
    claim(chapterId: string, content: string): boolean {
      if (!(content ?? "").trim()) return false;
      const key = summaryTriggerKey(chapterId, content);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    },
    get size(): number {
      return seen.size;
    },
  };
}
