import { describe, expect, it } from "vitest";
import type { PatientWithCount } from "../patients/api";
import { formatLastVisit, formatSince, sortInbox } from "./inbox";

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

describe("sortInbox por prioridad de visita", () => {
  it("dentro del mismo estado, lo más urgente de visitar va primero", () => {
    const patients = [
      { ...patient("Ana", "Box 1", "up_to_date"), priorityScore: 0.3 },
      { ...patient("Luis", "Box 2", "up_to_date"), priorityScore: 2.5 },
      { ...patient("Rosa", "Box 3", "up_to_date"), priorityScore: 1.1 },
      { ...patient("Juan", "Box 4", "review"), priorityScore: 0 },
    ];

    expect(sortInbox(patients).map((item) => item.name)).toEqual(["Juan", "Luis", "Rosa", "Ana"]);
  });
});

describe("sortInbox con conflictos", () => {
  it("dentro del mismo estado, los pacientes con conflictos tuyos van antes que los más urgentes de visitar", () => {
    const patients = [
      { ...patient("Ana", "Box 1", "up_to_date"), priorityScore: 3 },
      { ...patient("Luis", "Box 2", "up_to_date"), myOpenConflicts: 2, openConflicts: 2, priorityScore: 0.2 },
      { ...patient("Rosa", "Box 3", "up_to_date"), openConflicts: 1, priorityScore: 5 },
    ];

    expect(sortInbox(patients).map((item) => item.name)).toEqual(["Luis", "Rosa", "Ana"]);
  });
});

describe("formatLastVisit", () => {
  it("dice cuándo fue la última visita o que no hay", () => {
    const now = new Date("2026-11-21T12:00:00Z");
    expect(formatLastVisit("2026-11-21T11:07:00Z", now)).toBe("53 min");
    expect(formatLastVisit(null, now)).toBe("Sin visitas");
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
    criticality: "unknown",
    criticalityLabel: "Sin informe oficial",
    pendingTasks: 0,
    visitPriority: "unknown",
    visitPriorityLabel: "Sin datos",
    priorityScore: 0,
    processingStep: null,
    processingLabel: null,
    openConflicts: 0,
    myOpenConflicts: 0,
  };
}
