import { createFileRoute } from "@tanstack/react-router";
import { ReportsPage, type ReportsSearch } from "../../modules/reports/ReportsPage";

export const Route = createFileRoute("/_authenticated/reports")({
  validateSearch: (search: Record<string, unknown>): ReportsSearch => ({
    patient: typeof search.patient === "string" || typeof search.patient === "number" ? String(search.patient) : undefined,
    report: typeof search.report === "string" || typeof search.report === "number" ? String(search.report) : undefined,
    section: typeof search.section === "string" ? search.section : undefined,
    view: search.view === "summary" || search.view === "reports" ? search.view : undefined,
  }),
  component: ReportsRoute,
});

function ReportsRoute() {
  return <ReportsPage search={Route.useSearch()} />;
}
