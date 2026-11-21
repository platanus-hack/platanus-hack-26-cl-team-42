import { describe, expect, it } from "vitest";
import { DEMO_EPISODES } from "./testing/fixture";
import { buildHandoffSnapshots, handoffReferenceAt } from "./handoff";
import { summarizePatientStatus } from "./status";

const snapshots = buildHandoffSnapshots(DEMO_EPISODES, "prof-nurse-day");
const [snapshot] = snapshots;
const referenceAt = handoffReferenceAt(snapshots) ?? snapshot.cutoffAt;

describe("summarizePatientStatus", () => {
  it("resume DEMO-001 para Ana con la información al corte", () => {
    const status = summarizePatientStatus(snapshot, referenceAt);

    expect(status.lastEncounter).toEqual({
      occurredAt: "2026-11-20T16:40:00-03:00",
      authorId: "prof-nurse-day",
      elapsed: "2 h 50 min",
    });
    expect(status.pendings).toMatchObject({ open: 2, overdue: 0, nextDue: { id: "pend-abg" } });
    expect(status.openConflicts).toBe(1);
    expect(status.vitals).toHaveLength(4);
    expect(status.vitals).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "spo2", value: "95", unit: "%", flag: "normal" }),
      expect.objectContaining({ code: "hr", value: "88", flag: "normal" }),
      expect.objectContaining({ code: "rr", value: "24", flag: "high" }),
      expect.objectContaining({ code: "temp", value: "37,2", flag: "normal" }),
    ]));
  });

  it("cuenta como vencido un plazo igual a la referencia e ignora los plazos cerrados", () => {
    const [first, second, closed] = snapshot.pendings;
    const status = summarizePatientStatus({
      ...snapshot,
      pendings: [second, { ...closed, dueAt: referenceAt }, { ...first, dueAt: referenceAt }],
    }, referenceAt);

    expect(status.pendings).toEqual({ open: 2, overdue: 1, nextDue: second });
  });

  it("admite snapshots antiguos y marca valores no parseables", () => {
    const legacy = { ...snapshot };
    delete legacy.lastEncounter;
    const [datum] = legacy.cutoffData;
    legacy.cutoffData = [
      { ...datum, code: "spo2", value: "91" },
      { ...datum, code: "hr", value: "88 aprox." },
      { ...datum, code: "pa", value: "125/80", unit: "mmHg" },
      { ...datum, code: "other" },
    ];

    const status = summarizePatientStatus(legacy, referenceAt);
    expect(status.lastEncounter).toBeNull();
    expect(status.vitals.map(({ code, flag }) => ({ code, flag }))).toEqual([
      { code: "spo2", flag: "low" },
      { code: "hr", flag: "unknown" },
      { code: "pa", flag: "high" },
    ]);
  });
});
