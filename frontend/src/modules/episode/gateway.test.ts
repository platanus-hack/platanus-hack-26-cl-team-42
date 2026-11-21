import { expect, it, vi } from "vitest";
import { apiRequest } from "../../services/api/client";
import { episodeGateway } from "./gateway";
import { buildHandoffSnapshots } from "./handoff";
import { DEMO_EPISODE } from "./testing/fixture";

vi.mock("../../services/api/client", () => ({ apiRequest: vi.fn() }));

it("sends a fresh snapshot when the recipient hands off a received patient", async () => {
  const [received] = buildHandoffSnapshots([DEMO_EPISODE], "prof-nurse-day");
  const incoming = {
    id: "1",
    fromId: "prof-nurse-day",
    toId: "42",
    note: "",
    sentAt: received.cutoffAt,
    snapshots: [received],
  };
  const cutoffAt = "2026-11-21T08:00:00-03:00";
  const record = { ...DEMO_EPISODE, episode: { ...DEMO_EPISODE.episode, cutoffAt } };
  const request = vi.mocked(apiRequest);
  request.mockResolvedValueOnce([record]).mockResolvedValueOnce([incoming]).mockResolvedValueOnce({});

  await episodeGateway.sendHandoff({ fromId: "42", toId: "43", note: "", episodeIds: [received.episodeId] });

  expect(request).toHaveBeenCalledWith("/episodes/records");
  expect(request).toHaveBeenCalledWith("/episodes/handoffs");
  const [path, options] = request.mock.lastCall ?? [];
  expect(path).toBe("/episodes/handoffs");
  expect(options?.method).toBe("POST");
  expect(JSON.parse(String(options?.body))).toMatchObject({
    to_id: 43,
    snapshots: [{ episodeId: received.episodeId, cutoffAt }],
  });
});
