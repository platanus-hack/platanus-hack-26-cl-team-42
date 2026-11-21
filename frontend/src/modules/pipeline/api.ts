import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { apiRequest } from "../../services/api/client";
import { patientKeys } from "../patients/api";
import { reportKeys, type Report } from "../reports/api";
import type { Extraction } from "../templates/api";
import type { Transcript } from "../transcription/api";

// Estado de todas las etapas de un dictado (transcripción → parseo → informe) en una consulta.
// Backend: `GET /-/api/transcription/recordings/{id}/pipeline`.

export interface Pipeline {
  recordingId: string;
  transcription: Transcript | null;
  extraction: Extraction | null;
  report: Report | null;
}

const POLL_INTERVAL_MS = 1000;

export const pipelineKeys = ["pipeline"] as const;

export function usePipeline(recordingId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: [...pipelineKeys, recordingId],
    queryFn: () => apiRequest<Pipeline>(`/transcription/recordings/${recordingId}/pipeline`),
    refetchInterval: (current) => (current.state.data && isSettled(current.state.data) ? false : POLL_INTERVAL_MS),
  });

  const reportStatus = query.data?.report?.status;
  const reportReady = reportStatus === "review" || reportStatus === "done";
  useEffect(() => {
    if (!reportReady) return;
    void queryClient.invalidateQueries({ queryKey: reportKeys });
    void queryClient.invalidateQueries({ queryKey: patientKeys });
  }, [reportReady, queryClient]);

  return query;
}

/** Ya no hay nada más que esperar: el informe terminó o una etapa falló y requiere una acción. */
export function isSettled(pipeline: Pipeline): boolean {
  return (
    pipeline.transcription?.status === "failed" ||
    pipeline.extraction?.status === "failed" ||
    pipeline.report?.status === "review" ||
    pipeline.report?.status === "done" ||
    pipeline.report?.status === "failed"
  );
}
