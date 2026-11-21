import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, notConnected } from "../../services/api/client";

// Módulo 4 · Homologación de conceptos entre profesionales.

export type ConceptStatus = "pending" | "approved" | "rejected";

export interface ConceptMapping {
  id: string;
  /** Término tal como lo usó el profesional. */
  sourceTerm: string;
  sourceProfessional: string;
  /** Concepto canónico propuesto por el sistema, si lo hay. */
  suggestedConcept: string | null;
  /** Concepto canónico confirmado por una persona. */
  approvedConcept: string | null;
  status: ConceptStatus;
}

export interface ConceptsGateway {
  list(): Promise<ConceptMapping[]>;
  approve(id: string, canonicalConcept: string): Promise<ConceptMapping>;
}

export const conceptsGateway: ConceptsGateway = {
  list: () => apiRequest<ConceptMapping[]>("/transcription/concepts"),
  approve: notConnected("concepts.approve"),
};

export const conceptKeys = ["concept-mappings"] as const;

export function useConceptMappings() {
  return useQuery({
    queryKey: conceptKeys,
    queryFn: () => conceptsGateway.list(),
  });
}

export function useApproveConcept() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, canonicalConcept }: { id: string; canonicalConcept: string }) =>
      conceptsGateway.approve(id, canonicalConcept),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: conceptKeys }),
  });
}
