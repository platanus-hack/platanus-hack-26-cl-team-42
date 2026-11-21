import { createFileRoute } from "@tanstack/react-router";
import { ReconciliationPage } from "../../modules/reconciliation/ReconciliationPage";

export interface ReconciliationSearch {
  /** Reconciliación a mostrar seleccionada al llegar desde un aviso. */
  id?: string;
}

export const Route = createFileRoute("/_authenticated/reconciliation")({
  validateSearch: (search: Record<string, unknown>): ReconciliationSearch =>
    typeof search.id === "string" || typeof search.id === "number" ? { id: String(search.id) } : {},
  component: ReconciliationRoute,
});

function ReconciliationRoute() {
  const { id } = Route.useSearch();
  return <ReconciliationPage reconciliationId={id} />;
}
