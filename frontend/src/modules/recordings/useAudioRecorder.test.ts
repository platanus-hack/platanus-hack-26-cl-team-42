import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAudioRecorder } from "./useAudioRecorder";

describe("recording duration", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["performance", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
    });
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL = vi.fn().mockReturnValue("blob:recording");
      static revokeObjectURL = vi.fn();
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("counts the audio up to the stop request", async () => {
    const result = await startRecording();

    act(() => {
      vi.advanceTimersByTime(2375);
      result.current.stop();
      vi.advanceTimersByTime(500);
    });

    expect(result.current.audio?.durationSeconds).toBe(2.375);
  });

  it("counts both active segments when stopping after a resume", async () => {
    const result = await startRecording();

    act(() => {
      vi.advanceTimersByTime(2000);
      result.current.pause();
      vi.advanceTimersByTime(4000);
      result.current.resume();
      vi.advanceTimersByTime(1250);
      result.current.stop();
      vi.advanceTimersByTime(500);
    });

    expect(result.current.audio?.durationSeconds).toBe(3.25);
  });

  it("keeps the recorded duration when stopping while paused", async () => {
    const result = await startRecording();

    act(() => {
      vi.advanceTimersByTime(2000);
      result.current.pause();
      vi.advanceTimersByTime(4000);
      result.current.stop();
      vi.advanceTimersByTime(500);
    });

    expect(result.current.audio?.durationSeconds).toBe(2);
  });
});

async function startRecording() {
  const { result } = renderHook(useAudioRecorder);
  await act(() => result.current.start());
  return result;
}

class FakeMediaRecorder {
  readonly mimeType = "audio/webm";
  state: RecordingState = "inactive";
  ondataavailable?: (event: { data: Blob }) => void;
  onstop?: () => void;

  static isTypeSupported() {
    return true;
  }

  start() {
    this.state = "recording";
  }

  pause() {
    this.state = "paused";
  }

  resume() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    window.setTimeout(() => {
      this.ondataavailable?.({ data: new Blob(["audio"], { type: this.mimeType }) });
      this.onstop?.();
    }, 500);
  }
}
