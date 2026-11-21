import { describe, expect, it } from "vitest";
import { DEMO_EPISODE } from "./fixture";
import { renderRecordText, selectRecord, sourcedEntries } from "./record";

describe("selectRecord · invariante de corte", () => {
  const cutoff = Date.parse(DEMO_EPISODE.episode.cutoffAt);

  it("excluye atenciones posteriores al corte y entradas no validadas", () => {
    const view = selectRecord(DEMO_EPISODE);
    const ids = view.encounters.map((encounter) => encounter.id);

    expect(ids).not.toContain("enc-nurse-night-2");
    for (const encounter of view.encounters) {
      expect(Date.parse(encounter.occurredAt)).toBeLessThanOrEqual(cutoff);
      expect(encounter.entries.every((entry) => entry.status === "validated")).toBe(true);
    }
    expect(sourcedEntries(view).map((entry) => entry.entryId)).not.toContain("ent-md1-draft");
  });

  it("ordena las atenciones por hora clínica y agrupa varias entradas por atención", () => {
    const view = selectRecord(DEMO_EPISODE);
    const times = view.encounters.map((encounter) => Date.parse(encounter.occurredAt));
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(view.encounters.find((e) => e.id === "enc-med-day-1")?.entries).toHaveLength(2);
  });

  it("toma el último valor de cada variable antes del corte, con procedencia válida", () => {
    const view = selectRecord(DEMO_EPISODE);
    const spo2 = view.cutoffData.find((datum) => datum.code === "spo2");

    // 95 % (16:40) y no 90 % (21:10, posterior al corte).
    expect(spo2).toMatchObject({
      value: "95",
      source: { encounterId: "enc-nurse-day-1", entryId: "ent-nd1-vitals", authorId: "prof-nurse-day" },
    });
    const entryIds = new Set(sourcedEntries(view).map((entry) => entry.entryId));
    for (const datum of view.cutoffData) {
      expect(entryIds.has(datum.source.entryId)).toBe(true);
      expect(Date.parse(datum.observedAt)).toBeLessThanOrEqual(cutoff);
    }
  });

  it("el plan vigente es el último plan validado de cada disciplina", () => {
    const plan = selectRecord(DEMO_EPISODE).plan.map((item) => item.entryId);
    expect(plan).toEqual(expect.arrayContaining(["ent-md1-plan", "ent-kd1-plan", "ent-nd1-plan"]));
    expect(plan).not.toContain("ent-nn1-plan"); // reemplazado por el plan de enfermería de día
    expect(plan).toHaveLength(3);
  });

  it("filtrar por profesional deja datos, plan y pendientes coherentes con el filtro", () => {
    const view = selectRecord(DEMO_EPISODE, { professionalId: "prof-kine" });

    expect(view.encounters.map((e) => e.id)).toEqual(["enc-kine-day-1"]);
    expect(view.cutoffData).toEqual([
      expect.objectContaining({ code: "spo2", value: "94", source: expect.objectContaining({ authorId: "prof-kine" }) }),
    ]);
    expect(view.plan.map((item) => item.entryId)).toEqual(["ent-kd1-plan"]);
    expect(view.pendings.map((p) => p.id)).toEqual(["pend-kine-am"]);
  });

  it("filtrar por turno solo deja atenciones de ese turno", () => {
    const view = selectRecord(DEMO_EPISODE, { shiftId: "shift-night-19" });
    expect(view.encounters.map((e) => e.id)).toEqual(["enc-nurse-night-1"]);
    expect(view.cutoffData.find((d) => d.code === "spo2")?.value).toBe("92");
    // El turno de noche 20/11 empieza después del corte: queda vacío.
    expect(selectRecord(DEMO_EPISODE, { shiftId: "shift-night-20" }).encounters).toEqual([]);
  });

  it("el texto exportable se identifica como ficticio y respeta el filtro", () => {
    const text = renderRecordText(DEMO_EPISODE, selectRecord(DEMO_EPISODE, { professionalId: "prof-kine" }));
    expect(text).toContain("EPISODIO FICTICIO");
    expect(text).toContain("demo-episode-001");
    expect(text).toContain("Kinesioterapia respiratoria");
    expect(text).not.toContain("ceftriaxona");
    expect(text).not.toContain("sin validar");
  });

  it("mantiene los conflictos abiertos identificados y con sus atenciones de origen", () => {
    const view = selectRecord(DEMO_EPISODE);
    expect(view.openConflicts).toEqual([
      expect.objectContaining({ id: "conflict-o2-time", sourceEncounterIds: ["enc-nurse-day-1"] }),
    ]);
    expect(renderRecordText(DEMO_EPISODE, view)).toContain("CONFLICTOS POR REVISAR");
    expect(selectRecord(DEMO_EPISODE, { professionalId: "prof-kine" }).openConflicts).toEqual([]);
  });

  it("excluye los pendientes de atenciones posteriores al corte aun si los tiene el profesional filtrado", () => {
    const record = {
      ...DEMO_EPISODE,
      pendings: [
        ...DEMO_EPISODE.pendings,
        { ...DEMO_EPISODE.pendings[0], id: "pend-later", sourceEncounterId: "enc-nurse-night-2" },
      ],
    };
    const view = selectRecord(record, { professionalId: "prof-nurse-day" });

    expect(view.pendings.map((pending) => pending.id)).toEqual(["pend-abg"]);
  });
});
