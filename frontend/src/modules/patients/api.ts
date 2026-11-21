import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Pacientes asignados al profesional y su resumen.
// Backend: `backend/apps/recordings/patients_api.py` → `/-/api/patients`.

export interface Patient {
  id: number;
  name: string;
  /** RUT, ficha u otro identificador institucional. */
  identifier: string;
  bed: string;
  /** «Juan Pérez (12.345.678-9) · Cama 7» */
  reference: string;
}

/** Qué necesita el paciente de ti: un informe por validar, un dictado que falló o que aún se procesa. */
export type InboxStatus = "review" | "failed" | "processing" | "up_to_date";

export type PatientCriticality = "critical" | "high" | "moderate" | "stable" | "unknown";

/** Cuándo conviene volver a ver al paciente: ya toca, pronto, al día o sin datos. */
export type VisitPriority = "now" | "soon" | "ok" | "unknown";

export interface PatientWithCount extends Patient {
  reportCount: number;
  inboxStatus: InboxStatus;
  /** Último dictado de cualquier profesional del equipo. */
  lastDictationAt: string | null;
  /** Tu dictado cuya transcripción falló y se puede reintentar. */
  retryRecordingId: string | null;
  /** Criticidad según la versión oficial del paciente (`unknown` si aún no tiene). */
  criticality: PatientCriticality;
  criticalityLabel: string;
  /** Tareas por hacer: pendientes, indicaciones y recomendaciones. */
  pendingTasks: number;
  visitPriority: VisitPriority;
  visitPriorityLabel: string;
  /** Qué tan atrasada va la visita respecto de lo que pide su criticidad (mayor = más urgente). */
  priorityScore: number;
  /** Mientras se procesa un dictado tuyo: etapa (0 = en cola, 1 a 3) y su nombre. */
  processingStep: number | null;
  processingLabel: string | null;
  /** Conflictos abiertos entre informes de este paciente y cuántos son tuyos. */
  openConflicts: number;
  myOpenConflicts: number;
}

/** Etapas visibles de un dictado en proceso: transcribir, parsear a la plantilla y homologar. */
export const PROCESSING_STEPS = 3;

export interface Highlight {
  group: string;
  text: string;
  reportId: string;
  section: string;
  profession: string;
  authorName: string;
  at: string;
  severity: string;
}

export interface ProfessionActivity {
  profession: string;
  count: number;
  lastAt: string;
  lastAuthor: string;
  lastReportId: string;
}

export type CriticalityLevel = "critical" | "high" | "moderate" | "stable";

export interface Criticality {
  level: CriticalityLevel;
  label: string;
  reasons: string[];
}

/** Dato que conviene saber de inmediato: LET, no RCP, otras limitaciones y alergias. */
export interface KeyPoint {
  kind: "let" | "cpr" | "limit" | "allergy" | "full";
  label: string;
  detail: string;
  tone: "red" | "orange" | "gray" | "green";
}

export type AbnormalSeverity = "critical" | "high" | "moderate";

/** Examen de laboratorio o escala fuera de rango. */
export interface AbnormalFinding {
  kind: "lab" | "scale";
  name: string;
  value: string;
  unit: string;
  reference: string;
  severity: AbnormalSeverity;
  severityLabel: string;
  /** Ligado a mortalidad (SOFA, APACHE, lactato…): se destaca. */
  mortality: boolean;
  note: string;
  at: string | null;
  evidenceId: number | null;
  reportId: string | null;
}

export interface PatientSummary {
  patient: Omit<Patient, "reference">;
  reportCount: number;
  /** Versión oficial vigente de la que sale el resumen (0 si aún no hay). */
  version: number;
  versionReason: string;
  criticality: Criticality;
  /** Una línea con el día de estadía y el soporte actual. */
  status: string;
  /** Resumen muy breve del caso. */
  brief: string;
  synthesisPending: boolean;
  /** Puntos importantes bajo el resumen. */
  keyPoints: KeyPoint[];
  /** Pendientes del tratamiento: pendientes, indicaciones, recomendaciones y metas. */
  treatmentPending: Highlight[];
  /** Exámenes y escalas fuera de rango, lo más grave y ligado a mortalidad primero. */
  abnormal: AbnormalFinding[];
  byProfession: ProfessionActivity[];
  highlights: Highlight[];
}

/** Lo que dice el registro consolidado sobre un área clínica (hemodinamia, respiratorio…). */
export interface AreaSummary {
  area: string;
  /** Síntesis de 1 a 3 frases; vacía si el área aún no tiene información. */
  summary: string;
  informed: boolean;
  /** Secciones del registro que componen el área (para cruzarlas con los conflictos). */
  sections: string[];
  /** Profesiones (no personas) que aportaron datos a esta área. */
  contributors: string[];
}

/** Una profesión que aportó informes del paciente; nunca se identifica a la persona. */
export interface Contributor {
  profession: string;
  reportCount: number;
  /** Algún informe suyo choca con la versión oficial y espera reconciliarse. */
  inConflict: boolean;
}

export interface PatientOverview {
  version: number;
  /** Resumen global del caso: motivo de ingreso, evolución, intervenciones y situación actual. */
  globalSummary: string;
  synthesisPending: boolean;
  areas: AreaSummary[];
  /** Qué profesiones aportaron informes, en orden clínico habitual. */
  contributors: Contributor[];
}

export interface PatientVersion {
  version: number;
  /** `official` (primer informe), `merge` (sin conflictos) o `reconciliation` (conflictos resueltos). */
  reason: "official" | "merge" | "reconciliation";
  isCurrent: boolean;
  created_at: string;
  sourceReportId: string | null;
  sourceAuthor: string;
  sourceProfession: string;
}

export const patientKeys = ["patients"] as const;

const POLL_INTERVAL_MS = 3000;

export function usePatients() {
  return useQuery({
    queryKey: patientKeys,
    queryFn: () => apiRequest<PatientWithCount[]>("/patients"),
    // Mientras algún dictado se procesa, se consulta su avance.
    refetchInterval: (query) =>
      query.state.data?.some((patient) => patient.inboxStatus === "processing") ? POLL_INTERVAL_MS : false,
  });
}

export function usePatientSummary(patientId: number | undefined) {
  return useQuery({
    queryKey: [...patientKeys, patientId, "summary"],
    queryFn: ({ signal }) => apiRequest<PatientSummary>(`/patients/${patientId}/summary`, { signal }),
    enabled: patientId !== undefined,
    refetchInterval: (query) => query.state.data?.synthesisPending ? POLL_INTERVAL_MS : false,
  });
}

export type TrendStatus = "worsening" | "improving" | "stable" | "neutral";

/** Evolución de un examen o una escala (al menos dos mediciones). */
export interface Trend {
  kind: "lab" | "scale";
  name: string;
  unit: string;
  refMin: number | null;
  refMax: number | null;
  mortality: boolean;
  status: TrendStatus;
  /** Último valor menos el primero. */
  change: number;
  points: { at: string; value: number }[];
}

export function usePatientTrends(patientId: number | undefined) {
  return useQuery({
    queryKey: [...patientKeys, patientId, "trends"],
    queryFn: () => apiRequest<Trend[]>(`/patients/${patientId}/trends`),
    enabled: patientId !== undefined,
  });
}

/** Resumen global y síntesis por áreas de la versión oficial vigente. */
export function usePatientOverview(patientId: number | undefined) {
  return useQuery({
    queryKey: [...patientKeys, patientId, "overview"],
    queryFn: ({ signal }) => apiRequest<PatientOverview>(`/patients/${patientId}/overview`, { signal }),
    enabled: patientId !== undefined,
    refetchInterval: (query) => query.state.data?.synthesisPending ? POLL_INTERVAL_MS : false,
  });
}

/** Traspasa uno de tus pacientes a otro usuario; deja de estar asignado a ti. */
export function useTransferPatient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ patientId, toEmail }: { patientId: number; toEmail: string }) =>
      apiRequest<Patient>(`/patients/${patientId}/transfer`, {
        method: "POST",
        body: JSON.stringify({ to_email: toEmail }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: patientKeys }),
  });
}

/** Historial de versiones oficiales del paciente: las anteriores nunca se pierden. */
export function usePatientVersions(patientId: number) {
  return useQuery({
    queryKey: [...patientKeys, patientId, "versions"],
    queryFn: () => apiRequest<PatientVersion[]>(`/patients/${patientId}/versions`),
  });
}
