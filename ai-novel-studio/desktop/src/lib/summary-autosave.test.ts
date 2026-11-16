import { describe, expect, it } from "vitest";

import {
  contentFingerprint,
  createSummaryTriggerLog,
  summaryTriggerKey,
} from "@/lib/summary-autosave";

describe("contentFingerprint", () => {
  it("is stable for the same text and ignores surrounding whitespace", () => {
    expect(contentFingerprint("雨夜，铜铃响了。")).toBe(contentFingerprint("  雨夜，铜铃响了。\n"));
  });

  it("changes when the body changes", () => {
    expect(contentFingerprint("旧书店的门开了。")).not.toBe(contentFingerprint("旧书店的门关了。"));
    // Length-only edits must be caught too, not just same-length substitutions.
    expect(contentFingerprint("短句。")).not.toBe(contentFingerprint("长一点的句子。"));
  });
});

describe("summaryTriggerKey", () => {
  it("separates the same text in two different chapters", () => {
    expect(summaryTriggerKey("ch_1", "正文")).not.toBe(summaryTriggerKey("ch_2", "正文"));
  });
});

describe("createSummaryTriggerLog", () => {
  it("lets the same chapter + body through only once", () => {
    const log = createSummaryTriggerLog();

    expect(log.claim("ch_1", "雨夜，铜铃响了。")).toBe(true);
    // Flipping away and back must not fire a second paid request.
    expect(log.claim("ch_1", "雨夜，铜铃响了。")).toBe(false);
    expect(log.size).toBe(1);
  });

  it("re-arms as soon as the body changes", () => {
    const log = createSummaryTriggerLog();

    expect(log.claim("ch_1", "第一版")).toBe(true);
    expect(log.claim("ch_1", "第二版，多了两句。")).toBe(true);
    // …and then dedupes that new version too.
    expect(log.claim("ch_1", "第二版，多了两句。")).toBe(false);
    expect(log.size).toBe(2);
  });

  it("never triggers for a blank chapter", () => {
    const log = createSummaryTriggerLog();

    expect(log.claim("ch_1", "")).toBe(false);
    expect(log.claim("ch_1", "   \n\t ")).toBe(false);
    expect(log.size).toBe(0);
  });

  it("keeps separate chapters independent", () => {
    const log = createSummaryTriggerLog();

    expect(log.claim("ch_1", "同一段文字")).toBe(true);
    expect(log.claim("ch_2", "同一段文字")).toBe(true);
    expect(log.size).toBe(2);
  });
});
