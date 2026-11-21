import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { buildHandoffSnapshots } from "../episode/handoff";
import { DEMO_EPISODE, DEMO_EPISODE_ID } from "../episode/testing/fixture";
import { PatientStatusCard } from "./PatientStatusCard";

afterEach(cleanup);

it.each([false, true])("muestra la tarjeta de estado con snapshot antiguo: %s", (legacy) => {
  const [snapshot] = buildHandoffSnapshots([DEMO_EPISODE], "prof-nurse-day").filter(
    (item) => item.episodeId === DEMO_EPISODE_ID,
  );
  if (legacy) delete snapshot.lastEncounter;

  render(
    <Theme>
      <PatientStatusCard team={DEMO_EPISODE} snapshot={snapshot} referenceAt="2026-11-20T19:30:00-03:00" />
    </Theme>,
  );

  const card = within(screen.getByRole("region", { name: "Estado al corte" }));
  const encounterText = legacy ? "Sin atención registrada" : /Ana Morales \(Enfermera clínica\) · hace 2 h 50 min$/;
  expect(card.getByText(encounterText)).toBeInTheDocument();
  expect(card.getByText("SpO2")).toBeInTheDocument();
  expect(card.getByText("95 %")).toBeInTheDocument();
  expect(card.getByText("↑ alto")).toBeInTheDocument();
  if (!legacy) expect(card.getAllByText(/^· \d/).length).toBeGreaterThan(0);
});
