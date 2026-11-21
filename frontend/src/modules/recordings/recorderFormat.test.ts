import { describe, expect, it } from "vitest";
import { extensionFor, formatBytes, formatDuration, pickMimeType, rmsLevel } from "./recorderFormat";

describe("pickMimeType", () => {
  it("prefers opus in webm when supported", () => {
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus");
  });

  it("falls back to mp4 on Safari-like browsers", () => {
    expect(pickMimeType((type) => type === "audio/mp4")).toBe("audio/mp4");
  });

  it("returns undefined when nothing is supported", () => {
    expect(pickMimeType(() => false)).toBeUndefined();
  });
});

describe("extensionFor", () => {
  it("strips codec parameters", () => {
    expect(extensionFor("audio/webm;codecs=opus")).toBe("webm");
    expect(extensionFor("audio/mp4")).toBe("m4a");
    expect(extensionFor("application/x-unknown")).toBe("bin");
  });
});

describe("formatDuration", () => {
  it("formats minutes and hours", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(75.9)).toBe("01:15");
    expect(formatDuration(3675)).toBe("1:01:15");
  });

  it("handles unknown durations", () => {
    expect(formatDuration(null)).toBe("--:--");
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe("--:--");
  });
});

describe("formatBytes", () => {
  it("uses the largest sensible unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536 * 1024)).toBe("1,5 MB");
  });
});

describe("rmsLevel", () => {
  it("is zero for silence and capped at one", () => {
    expect(rmsLevel(new Uint8Array([128, 128, 128]))).toBe(0);
    expect(rmsLevel(new Uint8Array([0, 255, 0, 255]))).toBe(1);
  });
});
