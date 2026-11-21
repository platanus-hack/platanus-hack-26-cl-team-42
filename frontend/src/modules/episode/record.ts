import { formatClinicalTime } from "./format";
import type {
  ClinicalEntry,
  CutoffDatum,
  Discipline,
  Encounter,
  EpisodeRecord,
  OpenConflict,
  PendingTask,
  Professional,
  RecordFilter,
  SourcedEntry,
} from "./model";

/** Registro ya recortado: lo que se muestra, se copia a la ficha y se traspasa. */
export interface RecordView {
  filter: RecordFilter;
  /** Atenciones previas al corte, en orden clínico, solo con entradas validadas. */
  encounters: Encounter[];
  /** Último valor de cada variable medida antes del corte, con procedencia. */
  cutoffData: CutoffDatum[];
  /** Plan vigente: el último plan validado de cada disciplina. */
  plan: SourcedEntry[];
  pendings: PendingTask[];
  openConflicts: OpenConflict[];
}

/**
 * Aplica el invariante de corte: solo entran atenciones del episodio con hora
 * clínica ≤ corte y, de ellas, solo entradas validadas. Todo lo derivado
 * (datos de corte, plan, pendientes) sale de ese mismo subconjunto, así que
 * es coherente con el filtro.
 */
export function selectRecord(record: EpisodeRecord, filter: RecordFilter = {}): RecordView {
  const { episode } = record;
  const cutoff = Date.parse(episode.cutoffAt);
  const eligible = record.encounters
    .filter((encounter) => encounter.episodeId === episode.id)
    .filter((encounter) => Date.parse(encounter.occurredAt) <= cutoff)
    .map((encounter) => ({ ...encounter, entries: encounter.entries.filter(isValidated) }))
    .filter((encounter) => encounter.entries.length > 0)
    .sort(byOccurredAt);
  const encounters = eligible
    .filter((encounter) => !filter.professionalId || encounter.authorId === filter.professionalId)
    .filter((encounter) => !filter.shiftId || encounter.shiftId === filter.shiftId);

  const encounterIds = new Set(encounters.map((encounter) => encounter.id));
  const eligibleIds = new Set(eligible.map((encounter) => encounter.id));
  const pendings = record.pendings.filter(
    (pending) =>
      pending.episodeId === episode.id &&
      eligibleIds.has(pending.sourceEncounterId) &&
      (encounterIds.has(pending.sourceEncounterId) ||
        (!filter.shiftId && filter.professionalId !== undefined && pending.ownerId === filter.professionalId)),
  );
  const openConflicts = record.openConflicts.filter(
    (conflict) =>
      conflict.sourceEncounterIds.every((id) => eligibleIds.has(id)) &&
      conflict.sourceEncounterIds.some((id) => encounterIds.has(id)),
  );

  return {
    filter,
    encounters,
    cutoffData: cutoffDataOf(encounters),
    plan: currentPlanOf(encounters, record.professionals),
    pendings,
    openConflicts,
  };
}

/** Entradas validadas de la vista, aplanadas con su procedencia. */
export function sourcedEntries(view: RecordView): SourcedEntry[] {
  return view.encounters.flatMap((encounter) =>
    encounter.entries.map((entry) => toSourced(encounter, entry)),
  );
}

/** Id DOM de la tarjeta de una atención, para desplazarse hasta ella. */
export function encounterAnchor(encounterId: string): string {
  return `atencion-${encounterId}`;
}

export function professionalById(record: EpisodeRecord, id: string | null | undefined): Professional | undefined {
  return record.professionals.find((professional) => professional.id === id);
}

export const ENTRY_KIND_LABEL: Record<ClinicalEntry["kind"], string> = {
  assessment: "Evaluación",
  vitals: "Signos vitales",
  intervention: "Intervención",
  plan: "Plan",
};

export const DISCIPLINE_LABEL: Record<Discipline, string> = {
  nursing: "Enfermería",
  medicine: "Medicina",
  kinesiology: "Kinesiología",
};

/** Texto plano para pegar en la ficha institucional. Respeta el filtro de la vista. */
export function renderRecordText(record: EpisodeRecord, view: RecordView): string {
  const { episode } = record;
  const lines: string[] = [
    "EPISODIO FICTICIO — DATOS DE DEMOSTRACIÓN",
    `Episodio: ${episode.id} · ${episode.label} · ${episode.unit}`,
    `Corte: ${formatClinicalTime(episode.cutoffAt)}`,
    `Filtro: ${describeFilter(record, view.filter)}`,
    "",
    "ATENCIONES",
  ];
  if (view.encounters.length === 0) lines.push("(sin atenciones validadas)");
  for (const encounter of view.encounters) {
    lines.push(`— ${formatClinicalTime(encounter.occurredAt)} · ${authorLine(record, encounter.authorId)}`);
    for (const entry of encounter.entries) {
      lines.push(`  ${ENTRY_KIND_LABEL[entry.kind]}: ${entry.text}${measurementsText(entry)}`);
    }
  }
  lines.push("", "DATOS AL CORTE");
  if (view.cutoffData.length === 0) lines.push("(sin mediciones)");
  for (const datum of view.cutoffData) {
    lines.push(`  ${datumText(datum)} · ${formatClinicalTime(datum.observedAt)} · ${authorLine(record, datum.source.authorId)}`);
  }
  lines.push("", "PLAN VIGENTE");
  if (view.plan.length === 0) lines.push("(sin plan validado)");
  for (const item of view.plan) {
    lines.push(`  ${authorLine(record, item.authorId)}: ${item.text}`);
  }
  lines.push("", "PENDIENTES");
  if (view.pendings.length === 0) lines.push("(sin pendientes)");
  for (const pending of view.pendings) lines.push(`  ${pendingText(record, pending)}`);
  if (view.openConflicts.length > 0) {
    lines.push("", "CONFLICTOS POR REVISAR", ...view.openConflicts.map((conflict) => `  ${conflict.description}`));
  }
  return lines.join("\n");
}

export function describeFilter(record: EpisodeRecord, filter: RecordFilter): string {
  const parts: string[] = [];
  const professional = professionalById(record, filter.professionalId);
  if (professional) parts.push(`profesional ${professional.name}`);
  const shift = record.shifts.find((item) => item.id === filter.shiftId);
  if (shift) parts.push(`turno ${shift.label}`);
  return parts.length > 0 ? parts.join(" · ") : "episodio completo";
}

export function authorLine(record: EpisodeRecord, authorId: string | null | undefined): string {
  const author = professionalById(record, authorId);
  return author ? `${author.name} (${author.role})` : "Sin responsable";
}

export function datumText(datum: CutoffDatum): string {
  return `${datum.label} ${datum.value} ${datum.unit}`;
}

export function pendingText(record: EpisodeRecord, pending: PendingTask): string {
  const status = pending.status === "open" ? "ABIERTO" : "CERRADO";
  const due = pending.dueAt ? ` · plazo ${formatClinicalTime(pending.dueAt)}` : "";
  return `[${status}] ${pending.title} · responsable ${authorLine(record, pending.ownerId)}${due}`;
}

function isValidated(entry: ClinicalEntry): boolean {
  return entry.status === "validated";
}

function byOccurredAt(a: Encounter, b: Encounter): number {
  return Date.parse(a.occurredAt) - Date.parse(b.occurredAt);
}

function cutoffDataOf(encounters: Encounter[]): CutoffDatum[] {
  const latest = new Map<string, CutoffDatum>();
  for (const encounter of encounters) {
    for (const entry of encounter.entries) {
      for (const measurement of entry.measurements ?? []) {
        // `encounters` ya viene en orden clínico: el último escrito gana.
        latest.set(measurement.code, {
          ...measurement,
          observedAt: encounter.occurredAt,
          source: { encounterId: encounter.id, entryId: entry.id, authorId: encounter.authorId },
        });
      }
    }
  }
  return [...latest.values()];
}

function currentPlanOf(encounters: Encounter[], professionals: Professional[]): SourcedEntry[] {
  const latest = new Map<Discipline | string, SourcedEntry>();
  for (const encounter of encounters) {
    const discipline = professionals.find((p) => p.id === encounter.authorId)?.discipline ?? encounter.authorId;
    for (const entry of encounter.entries) {
      if (entry.kind === "plan") latest.set(discipline, toSourced(encounter, entry));
    }
  }
  return [...latest.values()];
}

function toSourced(encounter: Encounter, entry: ClinicalEntry): SourcedEntry {
  return {
    entryId: entry.id,
    encounterId: encounter.id,
    authorId: encounter.authorId,
    occurredAt: encounter.occurredAt,
    kind: entry.kind,
    text: entry.text,
  };
}

function measurementsText(entry: ClinicalEntry): string {
  if (!entry.measurements?.length) return "";
  return ` (${entry.measurements.map((m) => `${m.label} ${m.value} ${m.unit}`).join(", ")})`;
}
