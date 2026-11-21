import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 5 · Consolidación de informes de varios profesionales.

export interface ProfessionalReport {
  id: string;
  professionalName: string;
  specialty: string;
  /** Informe parseado (módulo 3) del que proviene. */
  parsedReportId: string;
}

export interface ConsolidatedSection {
  title: string;
  content: string;
  /** Informes de origen de esta sección, para trazabilidad. */
  sourceReportIds: string[];
}

export interface ConsolidatedReport {
  id: string;
  sourceReportIds: string[];
  sections: ConsolidatedSection[];
}

export interface ConsolidationGateway {
  listReports(): Promise<ProfessionalReport[]>;
  consolidate(reportIds: string[]): Promise<ConsolidatedReport>;
}

export const consolidationGateway: ConsolidationGateway = {
  listReports: async () => [],
  consolidate: notConnected("consolidation.consolidate"),
};

export const reportKeys = ["professional-reports"] as const;

export function useProfessionalReports() {
  return useQuery({
    queryKey: reportKeys,
    queryFn: () => consolidationGateway.listReports(),
  });
}

export function useConsolidateReports() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reportIds: string[]) => consolidationGateway.consolidate(reportIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reportKeys }),
  });
}
