import { createFileRoute } from "@tanstack/react-router";
import { InboxPage, type InboxSearch } from "../../modules/inbox/InboxPage";

export const Route = createFileRoute("/_authenticated/")({
  validateSearch: (search: Record<string, unknown>): InboxSearch => ({
    patient: optionalId(search.patient),
    report: optionalId(search.report),
    section: typeof search.section === "string" ? search.section : undefined,
    view: search.view === "reports" ? "reports" : undefined,
  }),
  component: InboxRoute,
});

function InboxRoute() {
  return <InboxPage search={Route.useSearch()} />;
}

function optionalId(value: unknown): string | undefined {
  return typeof value === "string" || typeof value === "number" ? String(value) : undefined;
}
