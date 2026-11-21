import { describe, expect, it } from "vitest";
import { DEMO_EPISODE, DEMO_EPISODE_ID } from "./fixture";
import { createDemoEpisodeGateway, memoryStore } from "./gateway";

function setup() {
  let counter = 0;
  const store = memoryStore();
  const gateway = createDemoEpisodeGateway({
    store,
    now: () => new Date("2026-11-20T19:45:00-03:00"),
    newId: () => `handoff-${++counter}`,
  });
  return { gateway, store };
}

const send = { episodeId: DEMO_EPISODE_ID, fromId: "prof-nurse-day", toId: "prof-kine", note: "  Ojo con SpO2 nocturna. " };

describe("demo episode gateway · traspasos", () => {
  it("guarda una copia fija del resumen, entradas, datos y pendientes al enviar", async () => {
    const { gateway } = setup();
    const handoff = await gateway.sendHandoff(send);

    expect(handoff).toMatchObject({ id: "handoff-1", fromId: "prof-nurse-day", toId: "prof-kine", note: "Ojo con SpO2 nocturna." });
    const { snapshot } = handoff;
    expect(snapshot.episodeId).toBe(DEMO_EPISODE_ID);
    expect(snapshot.summaryText).toContain("EPISODIO FICTICIO");
    expect(snapshot.summaryText).toContain("Conflictos por revisar");
    expect(snapshot.openConflicts).toEqual(DEMO_EPISODE.openConflicts);
    expect(snapshot.cutoffData.find((d) => d.code === "spo2")?.source.entryId).toBe("ent-nd1-vitals");
    expect(snapshot.pendings.find((p) => p.id === "pend-abg")?.status).toBe("open");
    // Cambios recientes: últimas 12 h antes del corte, sin borradores ni atenciones posteriores.
    const recent = snapshot.recentChanges.map((entry) => entry.entryId);
    expect(recent).not.toContain("ent-nn1-vitals");
    expect(recent).not.toContain("ent-md1-draft");
    expect(recent).not.toContain("ent-nn2-vitals");
    expect(recent[0]).toBe("ent-nd1-plan"); // más reciente primero
  });

  it("cerrar un pendiente no altera el envío anterior y un envío nuevo refleja el estado actual", async () => {
    const { gateway } = setup();
    const first = await gateway.sendHandoff(send);

    const closed = await gateway.closePending({
      episodeId: DEMO_EPISODE_ID,
      pendingId: "pend-abg",
      closedById: "prof-nurse-day",
    });
    expect(closed).toMatchObject({ status: "done", closedById: "prof-nurse-day" });

    const second = await gateway.sendHandoff({ ...send, note: "" });
    const [latest, earlier] = await gateway.listHandoffs(DEMO_EPISODE_ID);

    expect(latest.id).toBe(second.id);
    expect(earlier).toEqual(first);
    expect(earlier.snapshot.pendings.find((p) => p.id === "pend-abg")?.status).toBe("open");
    expect(earlier.snapshot.summaryText).toContain("[ABIERTO] Tomar gases arteriales");
    expect(latest.snapshot.pendings.find((p) => p.id === "pend-abg")?.status).toBe("done");
    expect(latest.snapshot.summaryText).toContain("[CERRADO] Tomar gases arteriales");
  });

  it("conserva el estado en el almacén entre instancias (recarga)", async () => {
    const { gateway, store } = setup();
    await gateway.sendHandoff(send);
    await gateway.closePending({ episodeId: DEMO_EPISODE_ID, pendingId: "pend-abg", closedById: "prof-med" });

    const reloaded = createDemoEpisodeGateway({ store });
    expect(await reloaded.listHandoffs(DEMO_EPISODE_ID)).toHaveLength(1);
    const record = await reloaded.getRecord(DEMO_EPISODE_ID);
    expect(record.pendings.find((p) => p.id === "pend-abg")?.status).toBe("done");

    await reloaded.reset(DEMO_EPISODE_ID);
    expect(await reloaded.listHandoffs(DEMO_EPISODE_ID)).toEqual([]);
    expect((await reloaded.getRecord(DEMO_EPISODE_ID)).pendings).toEqual(DEMO_EPISODE.pendings);
  });

  it("no muta el fixture ni expone referencias vivas", async () => {
    const { gateway } = setup();
    const record = await gateway.getRecord(DEMO_EPISODE_ID);
    record.pendings[0].status = "done";
    expect(DEMO_EPISODE.pendings[0].status).toBe("open");
    expect((await gateway.getRecord(DEMO_EPISODE_ID)).pendings[0].status).toBe("open");
  });

  it("rechaza episodios ajenos al fixture y envíos inválidos", async () => {
    const { gateway } = setup();
    await expect(gateway.getRecord("real-episode")).rejects.toThrow(/episodio ficticio/);
    await expect(gateway.sendHandoff({ ...send, toId: send.fromId })).rejects.toThrow(/otra persona/);
    await expect(gateway.sendHandoff({ ...send, toId: "nadie" })).rejects.toThrow(/desconocido/);
    await gateway.closePending({ episodeId: DEMO_EPISODE_ID, pendingId: "pend-abg", closedById: "prof-med" });
    await expect(
      gateway.closePending({ episodeId: DEMO_EPISODE_ID, pendingId: "pend-abg", closedById: "prof-med" }),
    ).rejects.toThrow(/ya está cerrado/);
  });
});
