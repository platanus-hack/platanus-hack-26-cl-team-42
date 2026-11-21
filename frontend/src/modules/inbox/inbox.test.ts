import { describe, expect, it } from "vitest";
import type { PatientWithCount } from "../patients/api";
import { formatSince, sortInbox } from "./inbox";

describe("sortInbox", () => {
  it("pone primero lo que requiere acción y luego ordena por cama", () => {
    const patients = [
      patient("Ana", "Box 9", "up_to_date"),
      patient("Luis", "Box 2", "processing"),
      patient("Rosa", "Box 10", "review"),
      patient("Juan", "Box 1", "up_to_date"),
      patient("Carlos", "Box 3", "failed"),
    ];

    expect(sortInbox(patients).map((item) => item.name)).toEqual(["Rosa", "Carlos", "Luis", "Juan", "Ana"]);
  });
});

describe("formatSince", () => {
  const now = new Date("2026-11-21T12:00:00Z");

  it.each([
    [null, "Sin dictados"],
    ["2026-11-21T11:59:50Z", "Ahora"],
    ["2026-11-21T11:45:00Z", "15 min"],
    ["2026-11-21T09:30:00Z", "2 h"],
    ["2026-11-20T10:00:00Z", "Ayer"],
    ["2026-11-18T10:00:00Z", "3 d"],
  ])("%s → %s", (iso, expected) => {
    expect(formatSince(iso, now)).toBe(expected);
  });
});

function patient(name: string, bed: string, inboxStatus: PatientWithCount["inboxStatus"]): PatientWithCount {
  return {
    id: name.length,
    name,
    identifier: "",
    bed,
    reference: name,
    reportCount: 0,
    inboxStatus,
    lastDictationAt: null,
    retryRecordingId: null,
  };
}
