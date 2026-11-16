import { describe, expect, it } from "vitest";

import { applyText } from "@/lib/text-edit";

const MANUSCRIPT = "第一段。\n\n第二段。";
const SELECTION = { start: 6, end: 10 }; // "第二段。"

describe("applyText", () => {
  it("replaces the selected range", () => {
    const result = applyText(MANUSCRIPT, SELECTION, "改写后的内容", "replace-selection");
    expect(result.content).toBe("第一段。\n\n改写后的内容");
    expect(result.caret).toBe("第一段。\n\n".length + "改写后的内容".length);
  });

  it("falls back to appending when the selection is collapsed", () => {
    // Never insert at an arbitrary caret: an empty selection means "no target".
    const result = applyText("abc", { start: 1, end: 1 }, "XY", "replace-selection");
    expect(result.content).toBe("abc\n\nXY");
    expect(result.caret).toBe(result.content.length);
  });

  it("appends as a new paragraph, trimming trailing whitespace", () => {
    const result = applyText("abc\n\n\n", null, "续写", "append");
    expect(result.content).toBe("abc\n\n续写");
    expect(result.caret).toBe(result.content.length);
  });

  it("appends to empty content without a leading blank line", () => {
    const result = applyText("", null, "第一章", "append");
    expect(result.content).toBe("第一章");
  });

  it("replaces the whole manuscript", () => {
    const result = applyText("old", { start: 0, end: 3 }, "brand new", "replace-all");
    expect(result.content).toBe("brand new");
    expect(result.caret).toBe(9);
  });

  it("clamps out-of-range selections", () => {
    const result = applyText("abc", { start: -5, end: 999 }, "X", "replace-selection");
    expect(result.content).toBe("X");
  });
});