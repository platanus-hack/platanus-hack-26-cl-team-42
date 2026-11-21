import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../services/api/client";

// Reconciliación de conflictos entre los informes de dos profesionales.
// Backend: `backend/apps/transcription` → `/-/api/transcription/{reconciliations,conflicts}`.

export interface ConflictSide {
  reportId: string | null;
  authorId: number | null;
  authorName: string;
  profession: string;
  /** El dato tal como lo reportó ese profesional. */
  value: string;
  /** Lo que dijo en el audio, que respalda el dato. */
  evidence: string;
}

export interface ConflictNote {
  id: string;
  /** `note` (de un profesional), `external` (opinión externa) o `system` (aviso del agente). */
  kind: "note" | "external" | "system";
  authorName: string;
  profession: string;
  body: string;
  created_at: string;
}

export interface ExternalConsult {
  id: string;
  consultantName: string;
  consultantProfession: string;
  status: "requested" | "answered";
  reply: string;
}

export interface Resolution {
  mode: "accepted" | "consensus" | "off_shift" | "sole";
  side: "a" | "b" | "custom";
  value: string;
  decidedByName: string;
  decidedAt: string;
}

export interface Proposal {
  by: number;
  byName: string;
  side: "a" | "b" | "custom";
  value?: string;
  label: string;
}

export interface ParticipantShift {
  name: string;
  profession: string;
  onShift: boolean;
}

export interface Guidance {
  suggestion: string;
  recommendedSide: "a" | "b" | "none";
  externalRecommended: boolean;
  externalProfession: string | null;
  externalReason: string;
  /** Profesional de turno que el sistema eligió para la opinión externa (null si no hay nadie). */
  externalCandidate: { name: string; profession: string } | null;
}

export interface Conflict {
  id: string;
  reconciliationId: string;
  key: string;
  /** `value`: mismo dato con valores distintos; `allergy`: indicación que contradice una alergia. */
  kind: "value" | "allergy";
  section: string;
  label: string;
  /** Por qué es un choque, explicado por el agente. */
  explanation: string;
  sideA: ConflictSide;
  sideB: ConflictSide;
  status: "open" | "resolved";
  resolution: Resolution | null;
  proposal: Proposal | null;
  /** Orientación del agente: ya viene generada al abrirse el conflicto. */
  guidance: Guidance | null;
  /** Quiénes participan y si están de turno ahora (la app lo sabe; nadie lo declara). */
  participantsShift: ParticipantShift[];
  notes: ConflictNote[];
  consults: ExternalConsult[];
  /** Cuál de los dos lados es tuyo: `a`, `b`, `both` o `null` si no participas. */
  myRole: "a" | "b" | "both" | null;
  /** Solo participas de la resolución si estás de turno. */
  iAmOnShift: boolean;
  canAccept: boolean;
  canAgree: boolean;
  canDecide: boolean;
}

export interface Reconciliation {
  id: string;
  status: "open" | "resolved";
  patientId: number;
  patientName: string;
  reportId: string;
  reportTitle: string;
  /** Quiénes participan: los autores de los informes que chocan. */
  participants: string[];
  baseVersion: number;
  resultVersion: number | null;
  conflicts: Conflict[];
  created_at: string;
  resolved_at: string | null;
}

export interface IncomingConsult {
  id: string;
  conflictId: string;
  /** El caso, sin datos del paciente ni de los profesionales. */
  brief: string;
  status: "requested" | "answered";
  reply: string;
  created_at: string;
}

export const reconciliationKeys = ["reconciliations"] as const;
export const consultKeys = ["external-consults"] as const;

const POLL_INTERVAL_MS = 4000;

/** Las reconciliaciones donde participas; se refrescan solas mientras haya alguna abierta. */
export function useReconciliations() {
  return useQuery({
    queryKey: reconciliationKeys,
    queryFn: () => apiRequest<Reconciliation[]>("/transcription/reconciliations"),
    refetchInterval: (query) => (query.state.data?.some((item) => item.status === "open") ? POLL_INTERVAL_MS : false),
  });
}

export function useIncomingConsults() {
  return useQuery({
    queryKey: consultKeys,
    queryFn: () => apiRequest<IncomingConsult[]>("/transcription/external-consults"),
  });
}

type ConflictAction =
  | { action: "notes"; body: { body: string } }
  | { action: "accept" }
  | { action: "propose"; body: { side?: "a" | "b"; value?: string } }
  | { action: "agree" }
  | { action: "decide"; body: { side?: "a" | "b"; value?: string } }
  | { action: "external" };

/** Cualquier acción sobre un conflicto; después se vuelve a pedir la lista. */
export function useConflictAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conflictId, ...request }: { conflictId: string } & ConflictAction) =>
      apiRequest<Conflict>(`/transcription/conflicts/${conflictId}/${request.action}`, {
        method: "POST",
        body: "body" in request ? JSON.stringify(request.body) : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: reconciliationKeys });
      // Al resolverse todo cambia la versión oficial y, con ella, el resumen y los informes.
      void queryClient.invalidateQueries({ queryKey: ["patients"] });
      void queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useReplyConsult() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ consultId, body }: { consultId: string; body: string }) =>
      apiRequest<IncomingConsult>(`/transcription/external-consults/${consultId}/reply`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: consultKeys }),
  });
}
