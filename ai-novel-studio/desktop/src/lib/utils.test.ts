import { describe, expect, it } from "vitest";

import {
  clamp,
  countWords,
  estimateTokens,
  formatCompact,
  formatNumber,
  formatRelativeTime,
  percent,
  readingMinutes,
} from "@/lib/utils";

describe("formatNumber", () => {
  it("formats thousands with separators", () => {
    expect(formatNumber(1_234_567)).toBe("1,234,567");
  });

  it("returns a dash for empty values", () => {
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
  });
});

describe("formatCompact", () => {
  it("shortens large counts", () => {
    expect(formatCompact(12_345)).toContain("万");
  });
});

describe("percent", () => {
  it("computes a bounded percentage", () => {
    expect(percent(50, 200)).toBe(25);
    expect(percent(0, 0)).toBe(0);
    expect(percent(500, 100)).toBe(100);
  });
});

describe("clamp", () => {
  it("keeps values inside the range", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(99, 0, 10)).toBe(10);
  });
});

describe("estimateTokens", () => {
  it("counts CJK characters close to one token each", () => {
    expect(estimateTokens("天地玄黄")).toBe(4);
  });

  it("returns zero for empty input", () => {
    expect(estimateTokens("")).toBe(0);
  });
});

describe("formatRelativeTime", () => {
  it("describes the current moment", () => {
    expect(formatRelativeTime(new Date().toISOString())).toBe("刚刚");
  });

  it("handles missing values", () => {
    expect(formatRelativeTime(null)).toBe("—");
  });
});

describe("countWords", () => {
  it("counts CJK characters one by one", () => {
    expect(countWords("天地玄黄")).toBe(4);
  });

  it("counts latin runs as single words", () => {
    expect(countWords("hello world")).toBe(2);
  });

  it("ignores whitespace and punctuation", () => {
    expect(countWords("天地玄黄，宇宙洪荒。\n\n")).toBe(8);
  });

  it("returns zero for empty text", () => {
    expect(countWords("")).toBe(0);
  });
});

describe("readingMinutes", () => {
  it("rounds up to at least one minute", () => {
    expect(readingMinutes(0)).toBe(0);
    expect(readingMinutes(400)).toBe(1);
    expect(readingMinutes(1200)).toBe(3);
  });
});