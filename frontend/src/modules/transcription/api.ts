import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 2 · Transcripción de los audios grabados.

export type TranscriptStatus = "queued" | "processing" | "done" | "failed";

export interface Transcript {
  id: string;
  recordingId: string;
  status: TranscriptStatus;
  language: string;
  text: string;
}

export interface TranscriptionGateway {
  list(): Promise<Transcript[]>;
  request(recordingId: string): Promise<Transcript>;
}

export const transcriptionGateway: TranscriptionGateway = {
  list: async () => [],
  request: notConnected("transcription.request"),
};

export const transcriptKeys = ["transcripts"] as const;

export function useTranscripts() {
  return useQuery({
    queryKey: transcriptKeys,
    queryFn: () => transcriptionGateway.list(),
  });
}

export function useRequestTranscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recordingId: string) => transcriptionGateway.request(recordingId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: transcriptKeys }),
  });
}
