import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";
import { extensionFor } from "../recordings/recorderFormat";
import { reportKeys } from "../reports/api";

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

/** Plantilla con su JSON Schema; `required` conserva el orden de las secciones. */
export interface FieldSchema {
  $ref?: string;
  description?: string;
  type?: string | string[];
  anyOf?: FieldSchema[];
  enum?: (string | number | boolean | null)[];
  properties?: Record<string, FieldSchema>;
  items?: FieldSchema;
  minimum?: number;
  maximum?: number;
}

export interface TemplateDetail extends ReportTemplate {
  output_schema: {
    required: string[];
    properties: Record<string, FieldSchema>;
    $defs?: Record<string, FieldSchema>;
  };
}

/** Información nueva para una sección: escrita y/o en audio. */
export interface SectionComplement {
  text?: string;
  audio?: Blob;
  audioFilename?: string;
}

export interface TemplatesGateway {
  listTemplates(): Promise<ReportTemplate[]>;
  getTemplate(slug: string, version?: number): Promise<TemplateDetail>;
  listExtractions(): Promise<Extraction[]>;
  extract(transcriptId: string, templateSlug?: string): Promise<Extraction>;
  complement(extractionId: string, section: string, complement: SectionComplement): Promise<Extraction>;
}

export const templatesGateway: TemplatesGateway = {
  listTemplates: () => apiRequest<ReportTemplate[]>("/clinical-templates/"),
  getTemplate: (slug, version) =>
    apiRequest<TemplateDetail>(`/clinical-templates/${slug}${version === undefined ? "" : `?version=${version}`}`),
  listExtractions: () => apiRequest<Extraction[]>("/transcription/extractions"),
  extract: (transcriptId, templateSlug) =>
    apiRequest<Extraction>(`/transcription/transcripts/${transcriptId}/extract`, {
      method: "POST",
      body: JSON.stringify({ template_slug: templateSlug ?? null }),
    }),
  complement: (extractionId, section, { text, audio, audioFilename }) => {
    const form = new FormData();
    form.append("section", section);
    if (text) form.append("text", text);
    if (audio) form.append("audio", audio, audioFilename ?? `complemento.${extensionFor(audio.type)}`);
    return apiRequest<Extraction>(`/transcription/extractions/${extractionId}/complement`, {
      method: "POST",
      body: form,
    });
  },
};

export const templateKeys = ["report-templates"] as const;
export const extractionKeys = ["extractions"] as const;

/** Mientras haya extracciones en curso se consulta su avance seguido, para ver cómo se llena. */
const POLL_INTERVAL_MS = 1500;

export function useReportTemplates() {
  return useQuery({
    queryKey: templateKeys,
    queryFn: () => templatesGateway.listTemplates(),
  });
}

export function useTemplate(slug: string | undefined, version?: number) {
  return useQuery({
    queryKey: [...templateKeys, slug, version],
    queryFn: () => templatesGateway.getTemplate(slug as string, version),
    enabled: slug !== undefined,
    staleTime: Infinity,
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
    mutationFn: ({ transcriptId, templateSlug }: { transcriptId: string; templateSlug?: string }) =>
      templatesGateway.extract(transcriptId, templateSlug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: extractionKeys }),
  });
}

export function useComplementSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      extractionId,
      section,
      ...complement
    }: { extractionId: string; section: string } & SectionComplement) =>
      templatesGateway.complement(extractionId, section, complement),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: extractionKeys });
      // El informe se vuelve a generar con la información nueva.
      void queryClient.invalidateQueries({ queryKey: reportKeys });
    },
  });
}

export function isExtractionInProgress(extraction: Extraction): boolean {
  return extraction.status === "pending" || extraction.status === "processing";
}
