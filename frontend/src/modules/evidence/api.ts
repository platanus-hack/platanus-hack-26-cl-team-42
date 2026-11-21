import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";
import { patientKeys } from "../patients/api";
import { reportKeys } from "../reports/api";

// Evidencia clínica del paciente además de los dictados: exámenes, imágenes, cultivos…
// Backend: `backend/apps/recordings/patients_api.py` → `/-/api/patients/{id}/evidence`.

export type EvidenceKind = "lab" | "imaging" | "culture" | "other";

export const EVIDENCE_KIND_LABEL: Record<EvidenceKind, string> = {
  lab: "Laboratorio",
  imaging: "Imagen",
  culture: "Cultivo",
  other: "Otro",
};

export interface EvidenceResult {
  name: string;
  value: string;
  unit: string;
  /** `high`/`low` si está fuera de su rango de referencia, `normal`, o vacío si no se puede juzgar. */
  flag: "high" | "low" | "normal" | "";
}

export interface EvidenceItem {
  id: number;
  kind: EvidenceKind;
  title: string;
  takenAt: string;
  results: EvidenceResult[];
  findings: string;
  createdByName: string;
}

export interface NewEvidence {
  kind: EvidenceKind;
  title: string;
  /** Cuándo se tomó la muestra o se hizo el examen (ISO). */
  takenAt: string;
  results: { name: string; value: string; unit: string }[];
  findings: string;
}

export const evidenceKeys = ["evidence"] as const;

export function useEvidence(patientId: number) {
  return useQuery({
    queryKey: [...evidenceKeys, patientId],
    queryFn: () => apiRequest<EvidenceItem[]>(`/patients/${patientId}/evidence`),
  });
}

export function useAddEvidence(patientId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (evidence: NewEvidence) =>
      apiRequest<EvidenceItem>(`/patients/${patientId}/evidence`, {
        method: "POST",
        body: JSON.stringify({
          kind: evidence.kind,
          title: evidence.title,
          taken_at: evidence.takenAt,
          results: evidence.results,
          findings: evidence.findings,
        }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: evidenceKeys });
      void queryClient.invalidateQueries({ queryKey: [...patientKeys, patientId] });
      // Los informes por validar del paciente se revisan de nuevo con la evidencia nueva.
      void queryClient.invalidateQueries({ queryKey: reportKeys });
    },
  });
}
