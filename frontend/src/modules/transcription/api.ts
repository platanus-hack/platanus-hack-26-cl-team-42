import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Módulo 2 · Transcripción automática de los audios cargados.

export interface Transcript {
  id: string;
  recordingId: string;
  name: string;
  status: "done";
  language: string;
  text: string;
  created_at: string;
}

export interface TranscriptionGateway {
  list(): Promise<Transcript[]>;
}

export const transcriptionGateway: TranscriptionGateway = {
  list: () => apiRequest<Transcript[]>("/transcription/transcripts"),
};

export const transcriptKeys = ["transcripts"] as const;

export function useTranscripts() {
  return useQuery({
    queryKey: transcriptKeys,
    queryFn: () => transcriptionGateway.list(),
  });
}
