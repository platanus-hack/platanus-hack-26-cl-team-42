import { describe, expect, it } from "vitest";
import { DEMO_EPISODES } from "./testing/fixture";
import { formatElapsed } from "./format";
import { buildHandoffSnapshots, handoffReferenceAt } from "./handoff";

describe("buildHandoffSnapshots", () => {
  it("records the latest encounter at cutoff for each patient", () => {
    const snapshots = buildHandoffSnapshots(DEMO_EPISODES, "prof-nurse-day");

    expect(snapshots.map(({ episodeId, lastEncounter }) => [episodeId, lastEncounter?.occurredAt])).toEqual(
      DEMO_EPISODES.filter(({ encounters }) => encounters.some(({ authorId }) => authorId === "prof-nurse-day")).map(
        ({ episode, encounters }) => [
          episode.id,
          encounters
            .filter(({ occurredAt }) => Date.parse(occurredAt) <= Date.parse(episode.cutoffAt))
            .map(({ occurredAt }) => occurredAt)
            .sort((a, b) => Date.parse(b) - Date.parse(a))[0],
        ],
      ),
    );
  });

  it("ignores encounters after the cutoff", () => {
    const [snapshot] = buildHandoffSnapshots(DEMO_EPISODES.slice(0, 1), "prof-nurse-day");

    expect(snapshot.lastEncounter).toMatchObject({ authorId: "prof-nurse-day", occurredAt: "2026-11-20T16:40:00-03:00" });
  });

  it("includes received patients still assigned to the recipient before they record an encounter", () => {
    const [received, unassigned] = buildHandoffSnapshots(DEMO_EPISODES, "prof-nurse-day");
    const [record, , otherRecord] = DEMO_EPISODES;
    const [other] = buildHandoffSnapshots([otherRecord], "prof-nurse-night");
    const savedHandoff = {
      id: "handoff-1",
      fromId: "prof-nurse-day",
      toId: "prof-fuentes",
      sentAt: received.cutoffAt,
      note: "",
      snapshots: [received, unassigned],
    };
    const records = [record, otherRecord];

    expect(buildHandoffSnapshots(records, "prof-fuentes")).toEqual([]);
    const snapshots = buildHandoffSnapshots(records, "prof-fuentes", [
      savedHandoff,
      { ...savedHandoff, id: "handoff-2", fromId: "prof-fuentes", toId: "someone-else", snapshots: [other] },
    ]);
    expect(snapshots.map(({ episodeId }) => episodeId)).toEqual([received.episodeId]);
  });
});

describe("handoffReferenceAt", () => {
  it("uses the latest cutoff", () => {
    const snapshots = buildHandoffSnapshots(DEMO_EPISODES, "prof-nurse-day");
    expect(handoffReferenceAt([{ ...snapshots[0], cutoffAt: "2026-11-20T18:00:00-03:00" }, snapshots[0]])).toBe(
      snapshots[0].cutoffAt,
    );
    expect(handoffReferenceAt([])).toBeUndefined();
  });
});

describe("formatElapsed", () => {
  it("formats hours and minutes", () => {
    expect(formatElapsed("2026-11-20T16:40:00-03:00", "2026-11-20T19:30:00-03:00")).toBe("2 h 50 min");
    expect(formatElapsed("2026-11-20T19:00:00-03:00", "2026-11-20T19:30:00-03:00")).toBe("30 min");
    expect(formatElapsed("2026-11-20T17:30:00-03:00", "2026-11-20T19:30:00-03:00")).toBe("2 h");
  });
});
