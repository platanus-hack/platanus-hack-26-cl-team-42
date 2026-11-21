import { describe, expect, it } from "vitest";
import { WORKFLOW_STEPS, getWorkflowStep } from "./workflow";

describe("workflow steps", () => {
  it("has unique ids and paths", () => {
    const ids = WORKFLOW_STEPS.map((step) => step.id);
    const paths = WORKFLOW_STEPS.map((step) => step.path);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("follows the recording-to-handoff order", () => {
    expect(WORKFLOW_STEPS.map((step) => step.id)).toEqual([
      "recordings",
      "transcription",
      "templates",
      "concepts",
      "consolidation",
      "actionables",
      "official-form",
      "handoff",
    ]);
  });

  it("returns no previous step for the first one and no next for the last", () => {
    const first = getWorkflowStep("recordings");
    const last = getWorkflowStep("handoff");
    expect(first.previous).toBeUndefined();
    expect(first.next?.id).toBe("transcription");
    expect(last.next).toBeUndefined();
    expect(last.previous?.id).toBe("official-form");
  });
});
