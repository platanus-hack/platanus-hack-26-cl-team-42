import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Consejo de agentes: discusión multiagente de una pregunta médica (libre o a partir de un conflicto).
// Backend: `backend/apps/transcription` → `/-/api/transcription/panels`.

export interface PanelTurn {
  round: number;
  profession: string;
  /** El rol que representa el agente («Médico UCI», «Kinesiología»…). */
  role: string;
  /** El profesional al que representa. */
  author: string;
  stance: string;
  body: string;
}

export interface PanelRecommendation {
  resumen: string;
  recomendacion: string;
  acuerdos: string[];
  desacuerdos: string[];
  siguientes_pasos: string[];
  confianza: "alta" | "media" | "baja";
  aviso: string;
}

export interface Panel {
  id: string;
  status: "pending" | "running" | "done" | "failed";
  patientId: number;
  patientName: string;
  conflictId: string | null;
  question: string;
  participants: string[];
  turns: PanelTurn[];
  recommendation: PanelRecommendation | null;
  error: string;
  created_at: string;
  finished_at: string | null;
}

const POLL_INTERVAL_MS = 3000;

export const panelKeys = ["panels"] as const;

export function isRunning(panel: Panel): boolean {
  return panel.status === "pending" || panel.status === "running";
}

/** Las consultas de un conflicto o de un paciente, más recientes primero; se refrescan mientras corren. */
export function usePanels(filter: { conflictId?: string; patientId?: number }) {
  const params = new URLSearchParams();
  if (filter.conflictId) params.set("conflict_id", filter.conflictId);
  if (filter.patientId !== undefined) params.set("patient_id", String(filter.patientId));
  return useQuery({
    queryKey: [...panelKeys, filter.conflictId ?? null, filter.patientId ?? null],
    queryFn: () => apiRequest<Panel[]>(`/transcription/panels?${params.toString()}`),
    refetchInterval: (query) => (query.state.data?.some(isRunning) ? POLL_INTERVAL_MS : false),
  });
}

/** Levanta una consulta: desde un conflicto (la pregunta es opcional) o una pregunta libre sobre un paciente. */
export function useOpenPanel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { conflictId?: string; patientId?: number; question?: string; areas?: string[] }) =>
      apiRequest<Panel>("/transcription/panels", {
        method: "POST",
        body: JSON.stringify({
          conflict_id: input.conflictId ? Number(input.conflictId) : undefined,
          patient_id: input.patientId,
          question: input.question ?? "",
          areas: input.areas ?? [],
        }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: panelKeys });
      // Al terminar deja una nota en la conversación del conflicto.
      void queryClient.invalidateQueries({ queryKey: ["reconciliations"] });
    },
  });
}
