import { describe, expect, it } from "vitest";
import { VISIBLE_STEPS, WORKFLOW_STEPS, getWorkflowStep } from "./workflow";

describe("workflow steps", () => {
  it("has unique ids and paths", () => {
    const ids = WORKFLOW_STEPS.map((step) => step.id);
    const paths = WORKFLOW_STEPS.map((step) => step.path);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("offers the patient inbox, the conflicts and the handoff", () => {
    expect(VISIBLE_STEPS.map((step) => step.id)).toEqual(["patients", "reconciliation", "handoff"]);
  });

  it("keeps the remaining steps hidden but defined", () => {
    expect(WORKFLOW_STEPS.map((step) => step.id)).toEqual([
      "patients",
      "recordings",
      "reports",
      "official-form",
      "reconciliation",
      "handoff",
      "transcription",
      "templates",
      "concepts",
      "consolidation",
      "actionables",
    ]);
  });

  it("links the visible steps to each other only", () => {
    const first = getWorkflowStep("patients");
    const last = getWorkflowStep("handoff");
    expect(first.previous).toBeUndefined();
    expect(first.next?.id).toBe("reconciliation");
    expect(last.previous?.id).toBe("reconciliation");
    expect(last.next).toBeUndefined();
  });

  it("places a hidden step within the full flow", () => {
    expect(getWorkflowStep("templates").previous?.id).toBe("transcription");
  });
});
