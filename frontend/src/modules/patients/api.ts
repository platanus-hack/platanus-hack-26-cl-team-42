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

export interface PatientWithCount extends Patient {
  reportCount: number;
  inboxStatus: InboxStatus;
  /** Último dictado de cualquier profesional del equipo. */
  lastDictationAt: string | null;
  /** Tu dictado cuya transcripción falló y se puede reintentar. */
  retryRecordingId: string | null;
}

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

export interface PatientSummary {
  patient: Omit<Patient, "reference">;
  reportCount: number;
  criticality: Criticality;
  /** Una línea con el día de estadía y el soporte actual. */
  status: string;
  /** Resumen muy breve del caso. */
  brief: string;
  /** Pendientes del tratamiento: pendientes, indicaciones, recomendaciones y metas. */
  treatmentPending: Highlight[];
  byProfession: ProfessionActivity[];
  highlights: Highlight[];
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
    queryFn: () => apiRequest<PatientSummary>(`/patients/${patientId}/summary`),
    enabled: patientId !== undefined,
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
