import { describe, expect, it } from "vitest";
import type { HandoffSnapshot, PendingTask } from "./model";
import { assessPriority, rankPatients } from "./priority";

describe("assessPriority", () => {
  it.each([
    ["15:31", "routine", 239 / 60],
    ["15:30", "attention", 4],
    ["11:31", "attention", 479 / 60],
    ["11:30", "critical", 8],
  ])("clasifica la última atención a las %s", (lastAt, level, hours) => {
    expect(assessPriority(patient("A", lastAt), referenceAt)).toMatchObject({
      level,
      hoursSinceLastEncounter: hours,
    });
  });

  it("incluye snapshots antiguos y pacientes sin atención", () => {
    const legacy = patient("A");
    delete legacy.lastEncounter;
    for (const snapshot of [legacy, { ...legacy, lastEncounter: null }]) {
      expect(assessPriority(snapshot, referenceAt)).toEqual({
        level: "attention",
        reasons: [{ level: "attention", text: "Sin atención registrada" }],
        hoursSinceLastEncounter: null,
      });
    }
  });

  it.each([
    ["19:29", "critical"],
    ["19:30", "critical"],
    ["19:31", "attention"],
    ["21:30", "attention"],
    ["21:31", "routine"],
  ])("clasifica un pendiente abierto con plazo a las %s", (dueAt, level) => {
    expect(assessPriority(patient("A", "19:00", [pending("Tarea", dueAt)]), referenceAt).level).toBe(level);
  });

  it("omite pendientes cerrados o sin plazo", () => {
    const snapshot = patient("A", "19:00", [pending("Cerrado", "18:00", "done"), pending("Sin plazo", null)]);
    expect(assessPriority(snapshot, referenceAt)).toMatchObject({ level: "routine", reasons: [] });
  });

  it("marca los conflictos abiertos", () => {
    expect(assessPriority({ ...patient("A"), openConflicts: [conflict] }, referenceAt)).toMatchObject({
      level: "attention",
      reasons: [{ level: "attention", text: "1 conflicto por revisar" }],
    });
  });

  it("usa el máximo y ordena las razones por gravedad", () => {
    const snapshot = {
      ...patient("A", "14:15", [pending("Coordinar visita", "21:00"), pending("Revisar plan", "19:00")]),
      openConflicts: [conflict],
    };
    expect(assessPriority(snapshot, referenceAt)).toEqual({
      level: "critical",
      hoursSinceLastEncounter: 5.25,
      reasons: [
        { level: "critical", text: "1 pendiente vencido: Revisar plan" },
        { level: "attention", text: "Vence en 1 h 30 min: Coordinar visita" },
        { level: "attention", text: "Última atención hace 5 h 15 min" },
        { level: "attention", text: "1 conflicto por revisar" },
      ],
    });
  });

  it("evalúa los mismos datos según el corte indicado", () => {
    const snapshot = patient("A", "14:15", [pending("Revisar plan", "19:30")]);
    expect(assessPriority(snapshot, at("16:00")).level).toBe("routine");
    expect(assessPriority(snapshot, referenceAt).level).toBe("critical");
  });
});

describe("rankPatients", () => {
  it("ordena por nivel, horas, pendientes vencidos y etiqueta", () => {
    const overdue = pending("Vencido", "18:00");
    const another = pending("También vencido", "19:00");
    const patients = [
      patient("1 hora", "18:30"),
      patient("D", "18:00", [overdue]),
      patient("Atención antigua", "10:00"),
      patient("A", "18:00", [overdue]),
      patient("2 horas", "17:30"),
      patient("Sin atención", null, [overdue]),
      patient("C", "18:00", [overdue, another]),
      patient("Conflicto", "14:00"),
      patient("Legacy", null),
      patient("Legacy anterior", null),
    ];

    expect(rankPatients(patients, referenceAt).map(({ snapshot, rank }) => [rank, snapshot.episodeLabel])).toEqual([
      [1, "Sin atención"],
      [2, "Atención antigua"],
      [3, "C"],
      [4, "A"],
      [5, "D"],
      [6, "Legacy"],
      [7, "Legacy anterior"],
      [8, "Conflicto"],
      [9, "2 horas"],
      [10, "1 hora"],
    ]);
  });
});

const referenceAt = at("19:30");
const conflict = { id: "conflict", description: "Plan por confirmar", sourceEncounterIds: [] };

function patient(label: string, lastAt: string | null = "19:00", pendings: PendingTask[] = []): HandoffSnapshot {
  return {
    episodeId: label,
    episodeLabel: label,
    cutoffAt: referenceAt,
    summaryText: "",
    recentChanges: [],
    plan: [],
    cutoffData: [],
    pendings,
    lastEncounter: lastAt ? { encounterId: "encounter", authorId: "author", occurredAt: at(lastAt) } : null,
  };
}

function pending(title: string, dueAt: string | null, status: PendingTask["status"] = "open"): PendingTask {
  return { id: title, title, episodeId: "A", dueAt: dueAt && at(dueAt), status, ownerId: null, sourceEncounterId: "encounter" };
}

function at(time: string) {
  return `2026-11-20T${time}:00-03:00`;
}
