import { describe, expect, it } from "vitest";
import { DEMO_EPISODE, DEMO_EPISODE_ID, DEMO_EPISODES, DEMO_OTHER_EPISODE_ID, DEMO_SECOND_EPISODE_ID } from "./fixture";
import { createDemoEpisodeGateway, memoryStore } from "./gateway";
import { buildHandoffSnapshots } from "./handoff";
import type { EpisodeRecord } from "./model";

const send = { fromId: "prof-nurse-day", toId: "prof-kine", note: "  Ojo con SpO2 nocturna. " };

describe("traspaso por profesional", () => {
  it("entrega una sola vez todos los pacientes atendidos por el emisor", async () => {
    const { gateway } = setup();
    const handoff = await gateway.sendHandoff(send);

    expect(handoff).toMatchObject({ id: "handoff-1", fromId: send.fromId, toId: send.toId, note: "Ojo con SpO2 nocturna." });
    expect(handoff.snapshots.map(({ episodeId }) => episodeId)).toEqual([DEMO_EPISODE_ID, DEMO_SECOND_EPISODE_ID]);
    expect(await gateway.listHandoffs(send.fromId)).toEqual([handoff]);
    expect(await gateway.listHandoffs(send.toId)).toEqual([handoff]);
    expect(await gateway.listHandoffs("prof-med")).toEqual([]);

    const [first, second] = handoff.snapshots;
    expect(first.summaryText).toContain("EPISODIO FICTICIO");
    expect(first.summaryText).toContain("Conflictos por revisar");
    expect(first.openConflicts).toEqual(DEMO_EPISODE.openConflicts);
    expect(first.cutoffData.find((datum) => datum.code === "spo2")?.source.entryId).toBe("ent-nd1-vitals");
    expect(first.plan).toContainEqual(expect.objectContaining({ authorId: "prof-med" }));
    expect(second.plan.map(({ entryId }) => entryId)).toEqual(["ent-demo-002-plan"]);

    const recent = first.recentChanges.map(({ entryId }) => entryId);
    expect(recent).not.toContain("ent-nn1-vitals");
    expect(recent).not.toContain("ent-md1-draft");
    expect(recent).not.toContain("ent-nn2-vitals");
    expect(recent[0]).toBe("ent-nd1-plan");
  });

  it("incluye al paciente con una atención en borrador y comparte solo las entradas validadas", async () => {
    const third = DEMO_EPISODES[2];
    const encounter = { ...third.encounters[0], authorId: send.fromId };
    const draft: EpisodeRecord = {
      ...third,
      encounters: [{ ...encounter, entries: [{ ...encounter.entries[0], status: "draft" }] }],
    };
    const { gateway } = setup([draft]);
    const handoff = await gateway.sendHandoff(send);
    expect(handoff.snapshots).toHaveLength(1);
    expect(handoff.snapshots[0]).toMatchObject({ episodeId: DEMO_OTHER_EPISODE_ID, recentChanges: [], plan: [] });
    expect(handoff.snapshots[0].summaryText).not.toContain(encounter.entries[0].text);
  });

  it("excluye pacientes si la única atención del emisor es posterior al corte", async () => {
    const third = DEMO_EPISODES[2];
    const afterCutoff: EpisodeRecord = {
      ...third,
      encounters: [{ ...third.encounters[0], authorId: send.fromId, occurredAt: "2026-11-21T07:40:00-03:00" }],
    };
    const { gateway } = setup([afterCutoff]);
    await expect(gateway.sendHandoff(send)).rejects.toThrow(/no tiene pacientes/);
    expect(await gateway.listHandoffs(send.toId)).toEqual([]);
  });

  it("actualiza el pendiente del paciente correcto y conserva el estado de toda la entrega anterior", async () => {
    const { gateway } = setup();
    const first = await gateway.sendHandoff(send);

    const closed = await gateway.closePending({
      episodeId: DEMO_SECOND_EPISODE_ID,
      pendingId: "pend-demo-002-movement",
      closedById: send.toId,
    });
    expect(closed).toMatchObject({ status: "done", closedById: send.toId });

    const second = await gateway.sendHandoff({ ...send, note: "" });
    const [latest, earlier] = await gateway.listHandoffs(send.toId);
    expect(latest.id).toBe(second.id);
    expect(earlier).toEqual(first);
    expect(latest.snapshots[0]).toEqual(earlier.snapshots[0]);
    expect(earlier.snapshots[1].pendings[0].status).toBe("open");
    expect(earlier.snapshots[1].summaryText).toContain("[ABIERTO] Coordinar la próxima movilización");
    expect(latest.snapshots[1].pendings[0].status).toBe("done");
    expect(latest.snapshots[1].summaryText).toContain("[CERRADO] Coordinar la próxima movilización");
  });

  it("conserva las entregas y los pendientes entre instancias y los restablece juntos", async () => {
    const { gateway, store } = setup();
    await gateway.sendHandoff(send);
    await gateway.closePending({ episodeId: DEMO_EPISODE_ID, pendingId: "pend-abg", closedById: "prof-med" });

    const reloaded = createDemoEpisodeGateway({ store });
    expect(await reloaded.listHandoffs(send.toId)).toHaveLength(1);
    expect((await reloaded.listRecords())[0].pendings[0].status).toBe("done");

    await reloaded.reset();
    expect(await reloaded.listHandoffs(send.toId)).toEqual([]);
    expect(await reloaded.listRecords()).toEqual(DEMO_EPISODES);
  });

  it("conserva las entregas anteriores de un solo paciente y sus cierres", async () => {
    const [{ episodeLabel: label, ...snapshot }] = buildHandoffSnapshots([DEMO_EPISODE], send.fromId);
    const closedAt = "2026-11-20T19:45:00-03:00";
    const store = memoryStore({
      version: 1,
      pendingClosures: { "pend-abg": { closedAt, closedById: send.toId } },
      handoffs: [{
        id: "legacy",
        ...send,
        sentAt: closedAt,
        episodeId: DEMO_EPISODE_ID,
        snapshot,
      }],
    });
    const gateway = createDemoEpisodeGateway({ store });

    const [handoff] = await gateway.listHandoffs(send.toId);
    expect(handoff).toMatchObject({ id: "legacy", snapshots: [{ episodeId: DEMO_EPISODE_ID, episodeLabel: label }] });
    expect(handoff.snapshots[0].pendings[0].status).toBe("open");
    expect((await gateway.listRecords())[0].pendings[0].status).toBe("done");
  });

  it("devuelve copias de los episodios y de las entregas", async () => {
    const { gateway } = setup();
    const [record] = await gateway.listRecords();
    record.pendings[0].status = "done";
    const handoff = await gateway.sendHandoff(send);
    handoff.snapshots[0].pendings[0].status = "done";

    expect((await gateway.listRecords())[0].pendings[0].status).toBe("open");
    expect((await gateway.listHandoffs(send.fromId))[0].snapshots[0].pendings[0].status).toBe("open");
  });

  it("valida los profesionales y que el pendiente pertenezca al episodio seleccionado", async () => {
    const { gateway } = setup();
    await expect(gateway.sendHandoff({ ...send, toId: send.fromId })).rejects.toThrow(/otra persona/);
    await expect(gateway.sendHandoff({ ...send, toId: "nadie" })).rejects.toThrow(/desconocido/);
    const close = { episodeId: DEMO_EPISODE_ID, pendingId: "pend-abg", closedById: "prof-med" };
    await expect(gateway.closePending({ ...close, episodeId: "real-episode" })).rejects.toThrow(/episodios ficticios/);
    await expect(gateway.closePending({ ...close, episodeId: DEMO_OTHER_EPISODE_ID })).rejects.toThrow(/Pendiente desconocido/);
    await gateway.closePending(close);
    await expect(gateway.closePending(close)).rejects.toThrow(/ya está cerrado/);
  });
});

function setup(fixtures = DEMO_EPISODES) {
  let counter = 0;
  const store = memoryStore();
  const gateway = createDemoEpisodeGateway({
    store,
    fixtures,
    now: () => new Date("2026-11-20T19:45:00-03:00"),
    newId: () => `handoff-${++counter}`,
  });
  return { gateway, store };
}
