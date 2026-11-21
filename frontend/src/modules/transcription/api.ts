import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiUrl } from "../../services/api/client";

// Módulo 2 · Transcripción automática de los dictados.
// Backend: `backend/apps/transcription` → `/-/api/transcription`. Cada dictado
// guardado se encola solo para transcribirse; aquí se consulta su avance.

export type TranscriptStatus = "pending" | "processing" | "done" | "failed";

export interface Transcript {
  id: string;
  recordingId: string;
  name: string;
  patientReference: string;
  /** Tipo de profesional del dictado; decide la plantilla clínica. */
  profession: string;
  specialty: string;
  recordedAt: string;
  durationSeconds: number | null;
  status: TranscriptStatus;
  language: string;
  text: string;
  /** Motivo legible cuando `status` es `failed`. */
  error: string;
  created_at: string;
}

export interface TranscriptionGateway {
  list(): Promise<Transcript[]>;
  retry(recordingId: string): Promise<Transcript>;
}

export const transcriptionGateway: TranscriptionGateway = {
  list: () => apiRequest<Transcript[]>("/transcription/transcripts"),
  retry: (recordingId) => apiRequest<Transcript>(`/transcription/recordings/${recordingId}`, { method: "POST" }),
};

export const transcriptKeys = ["transcripts"] as const;

/** Mientras haya transcripciones en curso, se consulta su avance cada pocos segundos. */
const POLL_INTERVAL_MS = 3000;

export function useTranscripts() {
  return useQuery({
    queryKey: transcriptKeys,
    queryFn: () => transcriptionGateway.list(),
    refetchInterval: (query) => (query.state.data?.some(isInProgress) ? POLL_INTERVAL_MS : false),
  });
}

export function useRetryTranscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recordingId: string) => transcriptionGateway.retry(recordingId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: transcriptKeys }),
  });
}

export function isInProgress(transcript: Transcript): boolean {
  return transcript.status === "pending" || transcript.status === "processing";
}

export function recordingAudioUrl(transcript: Transcript): string {
  return apiUrl(`/recordings/${transcript.recordingId}/audio`);
}
