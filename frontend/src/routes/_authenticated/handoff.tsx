import { createFileRoute } from "@tanstack/react-router";
import { HandoffPage } from "../../modules/handoff/HandoffPage";

export type HandoffTab = "send" | "received" | "sent";

export interface HandoffSearch {
  /** Profesional demo desde cuya perspectiva se mira el traspaso. */
  as?: string;
  tab?: HandoffTab;
  /** Traspaso abierto en la vista de enviados o recibidos. */
  handoff?: string;
}

const TABS: readonly HandoffTab[] = ["send", "received", "sent"];

export const Route = createFileRoute("/_authenticated/handoff")({
  validateSearch: (search: Record<string, unknown>): HandoffSearch => ({
    as: optionalString(search.as),
    tab: TABS.find((tab) => tab === search.tab),
    handoff: optionalString(search.handoff),
  }),
  component: HandoffRoute,
});

function HandoffRoute() {
  const search = Route.useSearch();
  return <HandoffPage search={search} />;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
