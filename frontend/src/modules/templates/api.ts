import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Módulo 3 · Parseo del texto transcrito a plantillas clínicas.
// Backend: `backend/apps/clinical_templates` (plantillas) y
// `backend/apps/transcription` (extracción con Qwen).

export interface ReportTemplate {
  slug: string;
  name: string;
  description: string;
  profession: string;
  version: number;
}

export type ExtractionStatus = "pending" | "processing" | "done" | "failed";

export interface Extraction {
  id: string;
  transcriptId: string;
  recordingId: string;
  templateSlug: string;
  templateName: string;
  status: ExtractionStatus;
  /** Registro estructurado según el JSON Schema de la plantilla. */
  data: Record<string, unknown> | null;
  /** Motivo legible cuando `status` es `failed`. */
  error: string;
  updated_at: string;
}

export interface TemplatesGateway {
  listTemplates(): Promise<ReportTemplate[]>;
  listExtractions(): Promise<Extraction[]>;
  extract(transcriptId: string, templateSlug: string): Promise<Extraction>;
}

export const templatesGateway: TemplatesGateway = {
  listTemplates: () => apiRequest<ReportTemplate[]>("/clinical-templates/"),
  listExtractions: () => apiRequest<Extraction[]>("/transcription/extractions"),
  extract: (transcriptId, templateSlug) =>
    apiRequest<Extraction>(`/transcription/transcripts/${transcriptId}/extract`, {
      method: "POST",
      body: JSON.stringify({ template_slug: templateSlug }),
    }),
};

export const templateKeys = ["report-templates"] as const;
export const extractionKeys = ["extractions"] as const;

/** Mientras haya extracciones en curso, se consulta su avance cada pocos segundos. */
const POLL_INTERVAL_MS = 3000;

export function useReportTemplates() {
  return useQuery({
    queryKey: templateKeys,
    queryFn: () => templatesGateway.listTemplates(),
  });
}

export function useExtractions() {
  return useQuery({
    queryKey: extractionKeys,
    queryFn: () => templatesGateway.listExtractions(),
    refetchInterval: (query) => (query.state.data?.some(isExtractionInProgress) ? POLL_INTERVAL_MS : false),
  });
}

export function useExtractRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ transcriptId, templateSlug }: { transcriptId: string; templateSlug: string }) =>
      templatesGateway.extract(transcriptId, templateSlug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: extractionKeys }),
  });
}

export function isExtractionInProgress(extraction: Extraction): boolean {
  return extraction.status === "pending" || extraction.status === "processing";
}
