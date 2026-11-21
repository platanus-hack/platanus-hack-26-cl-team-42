import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 1 · Grabación de audios por profesional.

export type RecordingStatus = "uploading" | "ready" | "failed";

export interface Recording {
  id: string;
  professionalName: string;
  durationSeconds: number;
  status: RecordingStatus;
  createdAt: string;
}

export interface RecordingsGateway {
  list(): Promise<Recording[]>;
  upload(audio: Blob): Promise<Recording>;
  remove(id: string): Promise<void>;
}

// Adaptador sin conexión: las lecturas devuelven vacío, las escrituras fallan explícitamente.
export const recordingsGateway: RecordingsGateway = {
  list: async () => [],
  upload: notConnected("recordings.upload"),
  remove: notConnected("recordings.remove"),
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
    mutationFn: (audio: Blob) => recordingsGateway.upload(audio),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recordingKeys }),
  });
}
