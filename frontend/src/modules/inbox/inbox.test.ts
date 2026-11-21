import { describe, expect, it } from "vitest";
import type { PatientWithCount } from "../patients/api";
import { formatLastVisit, formatSince, inboxRowState, inboxTier, sortInbox } from "./inbox";

describe("inboxTier", () => {
  it("rojo para la urgencia clínica, ámbar para lo que gestionar, verde al día y gris sin datos", () => {
    expect(inboxTier(known(patient("Ana", "Box 1", "up_to_date"), { criticality: "critical" }))).toBe("urgent");
    expect(inboxTier(known(patient("Ana", "Box 1", "up_to_date"), { visitPriority: "now" }))).toBe("urgent");
    expect(inboxTier(known(patient("Ana", "Box 1", "review")))).toBe("review");
    expect(inboxTier(known(patient("Ana", "Box 1", "failed")))).toBe("review");
    expect(inboxTier(known(patient("Ana", "Box 1", "up_to_date"), { myOpenConflicts: 1, openConflicts: 1 }))).toBe("review");
    expect(inboxTier(known(patient("Ana", "Box 1", "up_to_date"), { visitPriority: "soon" }))).toBe("review");
    expect(inboxTier(patient("Ana", "Box 1", "processing"))).toBe("processing");
    expect(inboxTier(known(patient("Ana", "Box 1", "up_to_date")))).toBe("ok");
    expect(inboxTier(patient("Ana", "Box 1", "up_to_date"))).toBe("no_data");
  });
});

describe("sortInbox", () => {
  it("ordena por número de cama y desempata por nombre, con las camas sin asignar al final", () => {
    const patients = [
      patient("Luis", "Box 2", "processing"),
      known(patient("Rosa", "Box 10", "review")),
      known(patient("Ana", "Box 2", "failed")),
      patient("Elena", " ", "up_to_date"),
      patient("Diego", "", "up_to_date"),
    ];

    expect(sortInbox(patients).map((item) => item.name)).toEqual(["Ana", "Luis", "Rosa", "Diego", "Elena"]);
  });

  it("conserva las posiciones cuando se resuelve un conflicto o cambia la urgencia", () => {
    const patients = [
      known(patient("Ana", "Box 1", "up_to_date"), { myOpenConflicts: 1, openConflicts: 1, priorityScore: 0.3 }),
      known(patient("Luis", "Box 2", "up_to_date"), { priorityScore: 0.5 }),
    ];
    const updated = [
      { ...patients[1], criticality: "critical", visitPriority: "now", priorityScore: 2 },
      { ...patients[0], myOpenConflicts: 0, openConflicts: 0 },
    ] satisfies PatientWithCount[];

    expect(sortInbox(patients).map((item) => item.name)).toEqual(["Ana", "Luis"]);
    expect(sortInbox(updated).map((item) => item.name)).toEqual(["Ana", "Luis"]);
  });
});

describe("inboxRowState", () => {
  const now = new Date("2026-11-21T12:00:00Z");

  it("un crítico por validar se ve rojo y conserva «Por validar» en el subtítulo", () => {
    const row = inboxRowState(known(patient("Ana", "Box 1", "review"), { criticality: "critical" }), now);
    expect(row.color).toBe("red");
    expect(row.badge).toEqual({ text: "Crítico", color: "red" });
    expect(row.secondary).toEqual(["Por validar"]);
  });

  it("la visita atrasada con conflictos muestra ambas señales", () => {
    const row = inboxRowState(
      known(patient("Luis", "Box 2", "up_to_date"), { visitPriority: "now", visitPriorityLabel: "Visitar ahora", myOpenConflicts: 2, openConflicts: 2 }),
      now,
    );
    expect(row.badge.text).toBe("Visitar ahora");
    expect(row.secondary).toEqual(["2 conflictos tuyos"]);
  });

  it("al día en verde con su contexto; sin datos en gris", () => {
    const ok = inboxRowState(known(patient("Rosa", "Box 3", "up_to_date"), { lastDictationAt: "2026-11-21T10:00:00Z" }), now);
    expect(ok.badge).toEqual({ text: "Al día", color: "green" });
    expect(ok.secondary).toEqual(["Estable", "Última visita 2 h"]);
    const empty = inboxRowState(patient("Sin", "Box 4", "up_to_date"), now);
    expect(empty.badge).toEqual({ text: "Sin datos", color: "gray" });
    expect(empty.secondary).toEqual(["Sin informe oficial"]);
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

/** Un paciente con versión oficial: estable y con la visita al día, salvo lo que se indique. */
function known(base: PatientWithCount, overrides: Partial<PatientWithCount> = {}): PatientWithCount {
  return {
    ...base,
    criticality: "stable",
    criticalityLabel: "Estable",
    visitPriority: "ok",
    visitPriorityLabel: "Visita al día",
    ...overrides,
  };
}
