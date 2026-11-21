import { formatClinicalTime } from "./format";
import type { EpisodeRecord, HandoffSnapshot, SourcedEntry } from "./model";
import { authorLine, datumText, pendingText, selectRecord, sourcedEntries } from "./record";

/** Ventana de «cambios recientes»: las últimas 12 h clínicas antes del corte. */
export const RECENT_WINDOW_HOURS = 12;

/**
 * Copia fija de lo que se comunica en un traspaso, tomada del episodio
 * completo al corte. Se clona en profundidad: cambios posteriores del
 * episodio (p. ej. cerrar un pendiente) no alteran envíos anteriores.
 */
export function buildHandoffSnapshot(record: EpisodeRecord): HandoffSnapshot {
  const view = selectRecord(record);
  const cutoff = Date.parse(record.episode.cutoffAt);
  const windowStart = cutoff - RECENT_WINDOW_HOURS * 60 * 60 * 1000;
  const recentChanges = sourcedEntries(view)
    .filter((entry) => Date.parse(entry.occurredAt) > windowStart)
    .reverse();

  const snapshot: HandoffSnapshot = {
    episodeId: record.episode.id,
    cutoffAt: record.episode.cutoffAt,
    summaryText: "",
    recentChanges,
    plan: view.plan,
    cutoffData: view.cutoffData,
    pendings: view.pendings,
    openConflicts: view.openConflicts,
  };
  snapshot.summaryText = renderHandoffSummary(record, snapshot);
  return structuredClone(snapshot);
}

/** Resumen en texto del traspaso; sale del propio snapshot, no del estado vivo. */
export function renderHandoffSummary(record: EpisodeRecord, snapshot: HandoffSnapshot): string {
  const lines = [
    "TRASPASO · EPISODIO FICTICIO (DEMO)",
    `${record.episode.label} · corte ${formatClinicalTime(snapshot.cutoffAt)}`,
    "",
    "Datos al corte:",
    ...snapshot.cutoffData.map((datum) => `  ${datumText(datum)}`),
    "",
    "Plan vigente:",
    ...snapshot.plan.map((item) => `  ${planLine(record, item)}`),
    "",
    "Pendientes:",
    ...snapshot.pendings.map((pending) => `  ${pendingText(record, pending)}`),
  ];
  if (snapshot.openConflicts?.length) {
    lines.push("", "Conflictos por revisar:", ...snapshot.openConflicts.map((conflict) => `  ${conflict.description}`));
  }
  return lines.join("\n");
}

function planLine(record: EpisodeRecord, item: SourcedEntry): string {
  return `${authorLine(record, item.authorId)}: ${item.text}`;
}
