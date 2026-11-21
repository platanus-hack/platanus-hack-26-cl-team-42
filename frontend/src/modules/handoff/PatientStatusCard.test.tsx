import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { DEMO_EPISODE_ID } from "../episode/fixture";
import { browserStore, createDemoEpisodeGateway } from "../episode/gateway";
import { HandoffPage } from "./HandoffPage";

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it.each([false, true])("muestra la tarjeta en Recibidos con snapshot antiguo: %s", async (legacy) => {
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  });

  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  });

  const store = browserStore(`demo-episode-state:${DEMO_EPISODE_ID}`);
  const gateway = createDemoEpisodeGateway({
    store,
    now: () => new Date("2026-11-20T19:30:00-03:00"),
    newId: () => "handoff-status-test",
  });
  const handoff = await gateway.sendHandoff({ fromId: "prof-nurse-day", toId: "prof-kine", note: "" });
  if (legacy) {
    for (const snapshot of handoff.snapshots) delete snapshot.lastEncounter;
    store.write({ version: 2, pendingClosures: {}, handoffs: [handoff] });
  }

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Theme><HandoffPage search={{ as: "prof-kine", tab: "received", handoff: handoff.id }} /></Theme>
    </QueryClientProvider>,
  );

  const patients = await screen.findByRole("group", { name: "Pacientes del traspaso" });
  fireEvent.click(within(patients).getByRole("button", { name: /DEMO-001/ }));
  const card = within(screen.getByRole("region", { name: "Estado al corte" }));
  const encounterText = legacy ? "Sin atención registrada" : /Última atención hace 2 h 50 min · Ana Morales/;
  expect(card.getByText(encounterText)).toBeInTheDocument();
  expect(card.getByText("SpO2")).toBeInTheDocument();
  expect(card.getByText("95")).toHaveTextContent("95 %");
  expect(card.getByText("Sobre el rango")).toBeInTheDocument();
  if (!legacy) expect(card.getByText(/^Medición:/)).toBeInTheDocument();
});
