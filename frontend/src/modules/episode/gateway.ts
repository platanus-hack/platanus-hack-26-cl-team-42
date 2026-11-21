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
}

export interface ClosePendingInput {
  episodeId: string;
  pendingId: string;
}

export const episodeGateway: EpisodeGateway = {
  listRecords: () => apiRequest<EpisodeRecord[]>("/episodes/records"),
  getTeam: () => apiRequest<Team>("/episodes/team"),
  closePending: ({ episodeId, pendingId }) =>
    apiRequest<PendingTask>(`/episodes/${episodeId}/pendings/${pendingId}/close`, { method: "POST" }),
  listHandoffs: () => apiRequest<Handoff[]>("/episodes/handoffs"),
  async sendHandoff({ fromId, toId, note, episodeIds }) {
    // La copia fija de lo comunicado se arma con el registro vigente de cada paciente elegido.
    const snapshots = buildHandoffSnapshots(await episodeGateway.listRecords(), fromId).filter(
      ({ episodeId }) => episodeIds.includes(episodeId),
    );
    if (snapshots.length === 0) throw new Error("Elige al menos un paciente con atenciones para traspasar.");
    return apiRequest<Handoff>("/episodes/handoffs", {
      method: "POST",
      body: JSON.stringify({ to_id: Number(toId), note, snapshots }),
    });
  },
};
