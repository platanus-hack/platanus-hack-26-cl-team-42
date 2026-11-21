import { createFileRoute } from "@tanstack/react-router";
import { ReconciliationPage } from "../../modules/reconciliation/ReconciliationPage";

export interface ReconciliationSearch {
  /** Reconciliación a mostrar seleccionada al llegar desde un aviso. */
  id?: string;
  conflict?: string;
}

export const Route = createFileRoute("/_authenticated/reconciliation")({
  validateSearch: (search: Record<string, unknown>): ReconciliationSearch => ({
    id: optionalId(search.id),
    conflict: optionalId(search.conflict),
  }),
  component: ReconciliationRoute,
});

function ReconciliationRoute() {
  const { id, conflict } = Route.useSearch();
  return <ReconciliationPage key={`${id ?? ""}:${conflict ?? ""}`} reconciliationId={id} conflictId={conflict} />;
}

function optionalId(value: unknown): string | undefined {
  return typeof value === "string" || typeof value === "number" ? String(value) : undefined;
}
