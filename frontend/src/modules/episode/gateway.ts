import { DEMO_EPISODE } from "./fixture";
import { buildHandoffSnapshot } from "./handoff";
import type { EpisodeRecord, Handoff, PendingTask, SendHandoffInput } from "./model";

/**
 * Adaptador del episodio clínico. Hoy lo sirve un gateway local de demo
 * limitado al episodio ficticio; mañana se sustituye por uno que hable con
 * la API real sin cambiar las vistas.
 */
export interface EpisodeGateway {
  getRecord(episodeId: string): Promise<EpisodeRecord>;
  closePending(input: ClosePendingInput): Promise<PendingTask>;
  listHandoffs(episodeId: string): Promise<Handoff[]>;
  sendHandoff(input: SendHandoffInput): Promise<Handoff>;
  /** Solo demo: vuelve al fixture original. */
  reset(episodeId: string): Promise<void>;
}

export interface ClosePendingInput {
  episodeId: string;
  pendingId: string;
  closedById: string;
}

/** Lo único que la demo persiste: cierres de pendientes y traspasos enviados. */
export interface DemoState {
  version: 1;
  pendingClosures: Record<string, { closedAt: string; closedById: string }>;
  handoffs: Handoff[];
}

/** Almacenamiento desacoplado del gateway (localStorage, memoria, …). */
export interface DemoStore {
  read(): DemoState | null;
  write(state: DemoState): void;
  clear(): void;
}

interface DemoGatewayOptions {
  store: DemoStore;
  fixture?: EpisodeRecord;
  now?: () => Date;
  newId?: () => string;
}

export function createDemoEpisodeGateway({
  store,
  fixture = DEMO_EPISODE,
  now = () => new Date(),
  newId = () => `handoff-${crypto.randomUUID()}`,
}: DemoGatewayOptions): EpisodeGateway {
  const load = (): DemoState => store.read() ?? emptyState();
  const assertEpisode = (episodeId: string) => {
    if (episodeId !== fixture.episode.id) {
      throw new Error(`La demo solo conoce el episodio ficticio "${fixture.episode.id}".`);
    }
  };
  const recordFrom = (state: DemoState): EpisodeRecord => {
    const record = structuredClone(fixture);
    record.pendings = record.pendings.map((pending) => {
      const closure = state.pendingClosures[pending.id];
      return closure ? { ...pending, status: "done", ...closure } : pending;
    });
    return record;
  };

  return {
    async getRecord(episodeId) {
      assertEpisode(episodeId);
      return recordFrom(load());
    },

    async closePending({ episodeId, pendingId, closedById }) {
      assertEpisode(episodeId);
      const state = load();
      const record = recordFrom(state);
      const pending = record.pendings.find((item) => item.id === pendingId);
      if (!pending) throw new Error(`Pendiente desconocido: ${pendingId}`);
      if (pending.status === "done") throw new Error("El pendiente ya está cerrado.");
      if (!record.professionals.some((p) => p.id === closedById)) {
        throw new Error(`Profesional desconocido: ${closedById}`);
      }
      const closure = { closedAt: now().toISOString(), closedById };
      store.write({ ...state, pendingClosures: { ...state.pendingClosures, [pendingId]: closure } });
      return { ...pending, status: "done", ...closure };
    },

    async listHandoffs(episodeId) {
      assertEpisode(episodeId);
      return structuredClone(load().handoffs);
    },

    async sendHandoff({ episodeId, fromId, toId, note }) {
      assertEpisode(episodeId);
      const state = load();
      const record = recordFrom(state);
      const known = (id: string) => record.professionals.some((p) => p.id === id);
      if (!known(fromId) || !known(toId)) throw new Error("Remitente o destinatario desconocido.");
      if (fromId === toId) throw new Error("El destinatario debe ser otra persona.");
      const handoff: Handoff = {
        id: newId(),
        episodeId,
        fromId,
        toId,
        note: note.trim(),
        sentAt: now().toISOString(),
        snapshot: buildHandoffSnapshot(record),
      };
      store.write({ ...state, handoffs: [handoff, ...state.handoffs] });
      return structuredClone(handoff);
    },

    async reset(episodeId) {
      assertEpisode(episodeId);
      store.clear();
    },
  };
}

export function memoryStore(initial: DemoState | null = null): DemoStore {
  let state = initial;
  return {
    read: () => (state ? structuredClone(state) : null),
    write: (next) => {
      state = structuredClone(next);
    },
    clear: () => {
      state = null;
    },
  };
}

/**
 * Persiste el estado de la demo en `localStorage` bajo una clave propia del
 * episodio ficticio. Si el navegador no lo permite, cae a memoria.
 */
export function browserStore(key: string): DemoStore {
  const fallback = memoryStore();
  return {
    read() {
      try {
        const raw = window.localStorage.getItem(key);
        const parsed = raw ? (JSON.parse(raw) as DemoState) : null;
        return parsed?.version === 1 ? parsed : fallback.read();
      } catch {
        return fallback.read();
      }
    },
    write(state) {
      fallback.write(state);
      try {
        window.localStorage.setItem(key, JSON.stringify(state));
      } catch {
        // Sin almacenamiento: la demo sigue en memoria hasta recargar.
      }
    },
    clear() {
      fallback.clear();
      try {
        window.localStorage.removeItem(key);
      } catch {
        // Nada que limpiar.
      }
    },
  };
}

function emptyState(): DemoState {
  return { version: 1, pendingClosures: {}, handoffs: [] };
}
