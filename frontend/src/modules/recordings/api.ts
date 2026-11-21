import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiUrl } from "../../services/api/client";
import { transcriptKeys } from "../transcription/api";
import type { Patient } from "../patients/api";
import { extensionFor } from "./recorderFormat";

// Módulo 1 · Obtención de datos: dictados de audio por profesional.
// Backend: `backend/apps/recordings` → `/-/api/recordings`.

export type RecordingSource = "in_app" | "upload";

export interface Recording {
  id: string;
  /** Nombre automático: cuenta · tipo de profesional · fecha y hora de la grabación. */
  name: string;
  professionalName: string;
  patientReference: string;
  /** Paciente al que pertenece el dictado (identifica de quién es). */
  patient: Patient | null;
  note: string;
  profession: string;
  specialty: string;
  mimeType: string;
  sizeBytes: number;
  durationSeconds: number | null;
  source: RecordingSource;
  recordedAt: string;
  createdAt: string;
  /** URL autenticada del audio, apta para `<audio src>`. */
  audioUrl: string;
}

export interface NewRecording {
  audio: Blob;
  source: RecordingSource;
  /** Nombre original (subidas); para grabaciones se deriva del MIME. */
  filename?: string;
  recordedAt?: Date;
  durationSeconds?: number | null;
  patientId?: number;
  note?: string;
  specialty?: string;
}

export interface RecordingsGateway {
  list(): Promise<Recording[]>;
  upload(recording: NewRecording): Promise<Recording>;
  remove(id: string): Promise<void>;
}

export const recordingsGateway: RecordingsGateway = {
  list: async () => (await apiRequest<RecordingDto[]>("/recordings")).map(fromDto),
  upload: async (recording) =>
    fromDto(await apiRequest<RecordingDto>("/recordings", { method: "POST", body: toFormData(recording) })),
  remove: (id) => apiRequest<void>(`/recordings/${id}`, { method: "DELETE" }),
};

export const recordingKeys = ["recordings"] as const;

export function useRecordings() {
  return useQuery({
    queryKey: recordingKeys,
    queryFn: () => recordingsGateway.list(),
  });
}

export function useUploadRecording() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recording: NewRecording) => recordingsGateway.upload(recording),
    onSuccess: () => {
      // Guardar un dictado encola su transcripción en el backend.
      void queryClient.invalidateQueries({ queryKey: recordingKeys });
      void queryClient.invalidateQueries({ queryKey: transcriptKeys });
    },
  });
}

export function useDeleteRecording() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => recordingsGateway.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recordingKeys }),
  });
}

interface RecordingDto {
  id: string;
  name: string;
  professional_name: string;
  patient_reference: string;
  patient: Patient | null;
  note: string;
  profession: string;
  specialty: string;
  mime_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  source: RecordingSource;
  recorded_at: string;
  created_at: string;
  audio_path: string;
}

function fromDto(dto: RecordingDto): Recording {
  return {
    id: dto.id,
    name: dto.name,
    professionalName: dto.professional_name,
    patientReference: dto.patient_reference,
    patient: dto.patient,
    note: dto.note,
    profession: dto.profession,
    specialty: dto.specialty,
    mimeType: dto.mime_type,
    sizeBytes: dto.size_bytes,
    durationSeconds: dto.duration_seconds,
    source: dto.source,
    recordedAt: dto.recorded_at,
    createdAt: dto.created_at,
    audioUrl: apiUrl(dto.audio_path),
  };
}

function toFormData(recording: NewRecording): FormData {
  const form = new FormData();
  const filename = recording.filename ?? `dictado.${extensionFor(recording.audio.type)}`;
  form.append("audio", recording.audio, filename);
  form.append("source", recording.source);
  if (recording.recordedAt) form.append("recorded_at", recording.recordedAt.toISOString());
  if (recording.durationSeconds != null) form.append("duration_seconds", String(recording.durationSeconds));
  if (recording.patientId !== undefined) form.append("patient_id", String(recording.patientId));
  if (recording.note) form.append("note", recording.note);
  if (recording.specialty) form.append("specialty", recording.specialty);
  return form;
}
