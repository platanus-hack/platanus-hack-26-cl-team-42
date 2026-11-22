import { apiRequest } from "../../services/api/client";
import { buildHandoffSnapshots } from "./handoff";
import type { EpisodeRecord, Handoff, PendingTask, Professional, SendHandoffInput } from "./model";

// Registro clínico y traspasos con datos reales.
// Backend: `backend/apps/transcription/episode_api.py` → `/-/api/episodes`.

export interface Team {
  /** Quién es el usuario activo. */
  meId: string;
  /** Todos los profesionales conocidos, para mostrar sus nombres y roles. */
  professionals: Professional[];
  /** A quiénes se puede traspasar (otros profesionales, no tú). */
  recipientIds: string[];
}

export interface EpisodeGateway {
  /** Un registro por cada paciente asignado al usuario activo. */
  listRecords(): Promise<EpisodeRecord[]>;
  getTeam(): Promise<Team>;
  closePending(input: ClosePendingInput): Promise<PendingTask>;
  /** Traspasos que el usuario activo envió o recibió. */
  listHandoffs(): Promise<Handoff[]>;
  sendHandoff(input: SendHandoffInput): Promise<Handoff>;
  /** Confirma que estas atenciones tuyas ya se pegaron en la ficha institucional. */
  markCharted(input: ChartInput): Promise<ChartResult>;
  /** Deshace la confirmación: vuelven a quedar por pasar. */
  unmarkCharted(input: ChartInput): Promise<ChartResult>;
}

export interface ClosePendingInput {
  episodeId: string;
  pendingId: string;
}

export interface ChartInput {
  episodeId: string;
  encounterIds: string[];
}

export interface ChartResult {
  encounterIds: string[];
}

export const episodeGateway: EpisodeGateway = {
  listRecords: () => apiRequest<EpisodeRecord[]>("/episodes/records"),
  getTeam: () => apiRequest<Team>("/episodes/team"),
  closePending: ({ episodeId, pendingId }) =>
    apiRequest<PendingTask>(`/episodes/${episodeId}/pendings/${pendingId}/close`, { method: "POST" }),
  listHandoffs: () => apiRequest<Handoff[]>("/episodes/handoffs"),
  markCharted: ({ episodeId, encounterIds }) =>
    apiRequest<ChartResult>(`/episodes/${episodeId}/charted`, {
      method: "POST",
      body: JSON.stringify({ encounter_ids: encounterIds }),
    }),
  unmarkCharted: ({ episodeId, encounterIds }) =>
    apiRequest<ChartResult>(`/episodes/${episodeId}/charted/undo`, {
      method: "POST",
      body: JSON.stringify({ encounter_ids: encounterIds }),
    }),
  async sendHandoff({ fromId, toId, note, episodeIds }) {
    const [records, handoffs] = await Promise.all([episodeGateway.listRecords(), episodeGateway.listHandoffs()]);
    // La copia fija de lo comunicado se arma con el registro vigente de cada paciente elegido.
    const snapshots = buildHandoffSnapshots(records, fromId, handoffs).filter(
      ({ episodeId }) => episodeIds.includes(episodeId),
    );
    if (snapshots.length === 0) throw new Error("Elige al menos un paciente para traspasar.");
    return apiRequest<Handoff>("/episodes/handoffs", {
      method: "POST",
      body: JSON.stringify({ to_id: Number(toId), note, snapshots }),
    });
  },
};
