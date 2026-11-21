import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 3 · Parseo del texto transcrito a plantillas de informe.

export interface TemplateField {
  key: string;
  label: string;
  required: boolean;
}

export interface ReportTemplate {
  id: string;
  name: string;
  fields: TemplateField[];
}

export interface ParsedReport {
  id: string;
  transcriptId: string;
  templateId: string;
  /** Valores extraídos del texto, indexados por `TemplateField.key`. */
  values: Record<string, string>;
}

export interface TemplatesGateway {
  listTemplates(): Promise<ReportTemplate[]>;
  parse(transcriptId: string, templateId: string): Promise<ParsedReport>;
}

export const templatesGateway: TemplatesGateway = {
  listTemplates: async () => [],
  parse: notConnected("templates.parse"),
};

export const templateKeys = ["report-templates"] as const;

export function useReportTemplates() {
  return useQuery({
    queryKey: templateKeys,
    queryFn: () => templatesGateway.listTemplates(),
  });
}

export function useParseTranscript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ transcriptId, templateId }: { transcriptId: string; templateId: string }) =>
      templatesGateway.parse(transcriptId, templateId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: templateKeys }),
  });
}
