import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Informes: el registro extraído con sus conceptos homologados, firmado por su autor.
// Backend: `backend/apps/transcription` → `/-/api/transcription/reports`.

/** `review`: homologado, a la espera de que su autor revise sus puntos pendientes; `done`: guardado (publicado; ya no se edita). */
export type ReportStatus = "processing" | "review" | "done" | "failed";

/** Un término del registro y el representante común al que se homologó. */
export interface Homologation {
  section: string;
  path: string;
  key: string;
  original: string;
  canonical: string;
  /** `dictionary` (conocido), `model` (propuesto ahora) o `unresolved` (sin homologar). */
  source: "dictionary" | "model" | "unresolved";
  /** `false` si el término ya era el representante común. */
  changed: boolean;
}

export interface ReportPatient {
  id: number;
  name: string;
  identifier: string;
  bed: string;
}

/** Contradicción entre el informe y la evidencia (exámenes) del paciente, para revisar al validar. */
export interface EvidenceAlert {
  id: string;
  /** `value` (valor o lectura distinta), `omission` (resultado alterado no mencionado) o `concept`. */
  kind: "value" | "omission" | "concept";
  severity: "high" | "medium";
  section: string;
  /** Tema del informe donde se muestra (coincide con `ReportTopic.id`). */
  topic: string;
  message: string;
  evidenceId: number | null;
  acknowledged: boolean;
}

/**
 * Punto que el autor debe revisar antes de guardar: un conflicto con la evidencia o una aclaración
 * (algo dictado que, por un dato que falta, no se puede interpretar o ejecutar tal cual).
 * El backend los entrega ordenados: primero los de severidad alta.
 */
export interface ReviewItem {
  id: string;
  kind: "evidence" | "clarification";
  /** `high`: conflicto clínicamente relevante (rojo); `medium`: discrepancia o aclaración (ámbar). */
  severity: "high" | "medium";
  section: string;
  message: string;
  /** Posición del ítem dictado dentro de la sección (si es una lista). */
  itemIndex: number | null;
  alertKind: EvidenceAlert["kind"] | null;
  evidenceId: number | null;
  evidenceTitle: string;
  evidenceTakenAt: string | null;
  fromEarlierVersion?: boolean;
  reviewed: boolean;
}

export interface ReportTopic {
  id: string;
  label: string;
  sections: string[];
}

export interface Report {
  id: string;
  extractionId: string;
  recordingId: string;
  templateSlug: string;
  templateName: string;
  templateVersion: number;
  status: ReportStatus;
  profession: string;
  patientReference: string;
  patient: ReportPatient | null;
  authorName: string;
  authorEmail: string;
  /** 1 = primer informe de esa categoría profesional para el paciente, 2 = segundo… */
  sequence: number;
  /** Registro con los conceptos ya homologados. */
  data: Record<string, unknown> | null;
  homologations: Homologation[];
  error: string;
  /** `pending`/`processing` mientras se incorpora información nueva al informe. */
  extractionStatus: "pending" | "processing" | "done" | "failed";
  /** Qué pasó al guardarse respecto de la versión oficial del paciente. */
  consolidation: "pending" | "official" | "merged" | "reconciling" | "consolidated";
  validatedAt: string | null;
  /** Temas del informe: agrupan sus secciones para leerlo completo (no se validan de a uno). */
  topics: ReportTopic[];
  /** Notas sin categoría (familia y observaciones), al final del informe completo. */
  noteSections: string[];
  /** Puntos por revisar (y ya revisados); sin pendientes, el autor puede guardar el informe. */
  reviewItems: ReviewItem[];
  evidenceAlerts: EvidenceAlert[];
  /** Solo quien generó el informe puede completarlo. */
  canEdit: boolean;
  editRevision: string;
  recordedAt: string;
  created_at: string;
  updated_at: string;
}

export interface AssistantReference {
  /** Informe y sección de origen, o `null` si la fuente es un examen (`evidenceId`). */
  reportId: string | null;
  section: string | null;
  evidenceId?: string | null;
  evidenceTitle?: string;
  patientId: number | null;
  patientName: string;
  profession: string;
  sequence: number;
  authorName: string;
  detail: string;
}

export interface AssistantAnswer {
  answer: string;
  references: AssistantReference[];
}

export const reportKeys = ["reports"] as const;

const POLL_INTERVAL_MS = 1500;

/** Informes de tus pacientes (de todos los profesionales), opcionalmente de uno solo. */
export function useReports(patientId?: number, includeDrafts = false) {
  const params = new URLSearchParams();
  if (patientId !== undefined) params.set("patient_id", String(patientId));
  if (includeDrafts) params.set("include_drafts", "true");
  const query = params.size > 0 ? `?${params}` : "";
  return useQuery({
    // Con borradores propios (para ofrecer «Informe por validar»); por defecto, solo guardados.
    queryKey: [...reportKeys, patientId ?? "all", includeDrafts ? "drafts" : "saved"],
    queryFn: () => apiRequest<Report[]>(`/transcription/reports${query}`),
    // Mientras un informe se completa o se rehomologa, se consulta su avance.
    refetchInterval: (query) => (query.state.data?.some(isReportBusy) ? POLL_INTERVAL_MS : false),
  });
}

/** Un informe concreto (también los borradores propios); se refresca mientras se completa. */
export function useReport(reportId: string, initial?: Report) {
  return useQuery({
    queryKey: [...reportKeys, "one", reportId],
    queryFn: () => apiRequest<Report>(`/transcription/reports/${reportId}`),
    initialData: initial,
    refetchInterval: (query) => (query.state.data && isReportBusy(query.state.data) ? POLL_INTERVAL_MS : false),
  });
}

export function useAskReports() {
  return useMutation({
    mutationFn: ({ question, patientId }: { question: string; patientId?: number }) =>
      apiRequest<AssistantAnswer>("/transcription/assistant/ask", {
        method: "POST",
        body: JSON.stringify({ question, patient_id: patientId ?? null }),
      }),
  });
}

/** Da por revisado un punto pendiente (una alerta queda marcada como revisada, no se borra). */
export function useReviewItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, itemId }: { reportId: string; itemId: string }) =>
      apiRequest<Report>(`/transcription/reports/${reportId}/review-items/${encodeURIComponent(itemId)}/review`, {
        method: "POST",
      }),
    onSuccess: (report) => {
      queryClient.setQueryData([...reportKeys, "one", report.id], report);
      return queryClient.invalidateQueries({ queryKey: reportKeys });
    },
  });
}

interface ReportItemEdit {
  reportId: string;
  section: string;
  index?: number;
  value: unknown;
  revision: string;
}

export function useEditReportItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, section, index, value, revision }: ReportItemEdit) =>
      apiRequest<Report>(`/transcription/reports/${reportId}/sections/${encodeURIComponent(section)}`, {
        method: "PATCH",
        body: JSON.stringify({ index, value, revision }),
      }),
    onSuccess: (report) => {
      queryClient.setQueryData([...reportKeys, "one", report.id], report);
      void queryClient.invalidateQueries({ queryKey: reportKeys });
      void queryClient.invalidateQueries({ queryKey: ["extractions"] });
      void queryClient.invalidateQueries({ queryKey: ["pipeline"] });
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: reportKeys });
    },
  });
}

/** Guarda el informe sin puntos pendientes: se publica al equipo del paciente y ya no se edita. */
export function useValidateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reportId: string) => apiRequest<Report>(`/transcription/reports/${reportId}/validate`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: reportKeys });
      void queryClient.invalidateQueries({ queryKey: ["patients"] });
      void queryClient.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}

export function isReportBusy(report: Report): boolean {
  return report.status === "processing" || report.extractionStatus === "pending" || report.extractionStatus === "processing";
}
