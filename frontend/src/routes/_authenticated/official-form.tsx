import { createFileRoute } from "@tanstack/react-router";
import { ClinicalRecordPage } from "../../modules/clinical-record/ClinicalRecordPage";

export interface ClinicalRecordSearch {
  /** Filtro por autor de la atención. */
  professional?: string;
  /** Filtro por turno. */
  shift?: string;
  /** Atención de origen a destacar (enlaces desde traspasos y datos de corte). */
  encounter?: string;
}

export const Route = createFileRoute("/_authenticated/official-form")({
  validateSearch: (search: Record<string, unknown>): ClinicalRecordSearch => ({
    professional: optionalString(search.professional),
    shift: optionalString(search.shift),
    encounter: optionalString(search.encounter),
  }),
  component: ClinicalRecordRoute,
});

function ClinicalRecordRoute() {
  const search = Route.useSearch();
  return <ClinicalRecordPage search={search} />;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
