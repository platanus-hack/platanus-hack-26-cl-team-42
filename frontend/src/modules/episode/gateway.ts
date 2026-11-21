import { DEMO_EPISODE_ID, DEMO_EPISODES } from "./fixture";
import { buildHandoffSnapshots } from "./handoff";
import type { EpisodeRecord, Handoff, HandoffSnapshot, PendingTask, SendHandoffInput } from "./model";

export interface EpisodeGateway {
  listRecords(): Promise<EpisodeRecord[]>;
  closePending(input: ClosePendingInput): Promise<PendingTask>;
  listHandoffs(professionalId: string): Promise<Handoff[]>;
  sendHandoff(input: SendHandoffInput): Promise<Handoff>;
  reset(): Promise<void>;
}

export interface ClosePendingInput {
  episodeId: string;
  pendingId: string;
  closedById: string;
}

type PendingClosures = Record<string, { closedAt: string; closedById: string }>;

interface DemoState {
  version: 2;
  pendingClosures: Record<string, PendingClosures>;
  handoffs: Handoff[];
}

type LegacyHandoff = Omit<Handoff, "snapshots"> & {
  episodeId: string;
  snapshot: Omit<HandoffSnapshot, "episodeLabel">;
};

interface LegacyDemoState {
  version: 1;
  pendingClosures: PendingClosures;
  handoffs: LegacyHandoff[];
}

type StoredState = DemoState | LegacyDemoState;

export interface DemoStore {
  read(): StoredState | null;
  write(state: DemoState): void;
  clear(): void;
}

interface DemoGatewayOptions {
  store: DemoStore;
  fixtures?: EpisodeRecord[];
  now?: () => Date;
  newId?: () => string;
}

export function createDemoEpisodeGateway({
  store,
  fixtures = DEMO_EPISODES,
  now = () => new Date(),
  newId = () => `handoff-${crypto.randomUUID()}`,
}: DemoGatewayOptions): EpisodeGateway {
  const professionals = new Set(fixtures.flatMap(({ professionals }) => professionals.map(({ id }) => id)));
  const load = () => upgradeState(store.read(), fixtures);

  return {
    async listRecords() {
      const state = load();
      return fixtures.map((fixture) => recordFrom(fixture, state));
    },

    async closePending({ episodeId, pendingId, closedById }) {
      const fixture = fixtures.find(({ episode }) => episode.id === episodeId);
      if (!fixture) throw new Error("La demo solo admite episodios ficticios conocidos.");
      if (!fixture.professionals.some(({ id }) => id === closedById)) {
        throw new Error("Profesional desconocido.");
      }

      const state = load();
      const record = recordFrom(fixture, state);
      const pending = record.pendings.find((item) => item.id === pendingId);
      if (!pending) throw new Error(`Pendiente desconocido: ${pendingId}`);
      if (pending.status === "done") throw new Error("El pendiente ya está cerrado.");

      const closure = { closedAt: now().toISOString(), closedById };
      store.write({
        ...state,
        pendingClosures: {
          ...state.pendingClosures,
          [episodeId]: { ...state.pendingClosures[episodeId], [pendingId]: closure },
        },
      });
      return { ...pending, status: "done", ...closure };
    },

    async listHandoffs(professionalId) {
      if (!professionals.has(professionalId)) throw new Error("Profesional desconocido.");
      return structuredClone(
        load().handoffs.filter(({ fromId, toId }) => fromId === professionalId || toId === professionalId),
      );
    },

    async sendHandoff({ fromId, toId, note }) {
      if (!professionals.has(fromId) || !professionals.has(toId)) {
        throw new Error("Remitente o destinatario desconocido.");
      }
      if (fromId === toId) throw new Error("El destinatario debe ser otra persona.");

      const state = load();
      const records = fixtures.map((fixture) => recordFrom(fixture, state));
      const snapshots = buildHandoffSnapshots(records, fromId);
      if (snapshots.length === 0) throw new Error("El profesional no tiene pacientes para traspasar.");

      const handoff: Handoff = {
        id: newId(),
        fromId,
        toId,
        note: note.trim(),
        sentAt: now().toISOString(),
        snapshots,
      };
      store.write({ ...state, handoffs: [handoff, ...state.handoffs] });
      return structuredClone(handoff);
    },

    async reset() {
      store.clear();
    },
  };
}

export function memoryStore(initial: StoredState | null = null): DemoStore {
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

export function browserStore(key: string): DemoStore {
  const fallback = memoryStore();
  return {
    read() {
      try {
        const raw = window.localStorage.getItem(key);
        const parsed = raw ? (JSON.parse(raw) as StoredState) : null;
        return parsed?.version === 1 || parsed?.version === 2 ? parsed : fallback.read();
      } catch {
        return fallback.read();
      }
    },
    write(state) {
      fallback.write(state);
      try {
        window.localStorage.setItem(key, JSON.stringify(state));
      } catch {
        // Los cambios se conservan en memoria hasta recargar.
      }
    },
    clear() {
      fallback.clear();
      try {
        window.localStorage.removeItem(key);
      } catch {
        // El navegador puede impedir el acceso a localStorage.
      }
    },
  };
}

function recordFrom(fixture: EpisodeRecord, state: DemoState): EpisodeRecord {
  const record = structuredClone(fixture);
  const closures = state.pendingClosures[record.episode.id] ?? {};
  record.pendings = record.pendings.map((pending) => {
    const closure = closures[pending.id];
    return closure ? { ...pending, status: "done", ...closure } : pending;
  });
  return record;
}

function upgradeState(state: StoredState | null, fixtures: EpisodeRecord[]): DemoState {
  if (!state) return { version: 2, pendingClosures: {}, handoffs: [] };
  if (state.version === 2) return state;

  return {
    version: 2,
    pendingClosures: { [DEMO_EPISODE_ID]: state.pendingClosures },
    handoffs: state.handoffs.map(({ episodeId, snapshot, ...handoff }) => ({
      ...handoff,
      snapshots: [{
        ...snapshot,
        episodeLabel: fixtures.find(({ episode }) => episode.id === episodeId)?.episode.label ?? episodeId,
      }],
    })),
  };
}
