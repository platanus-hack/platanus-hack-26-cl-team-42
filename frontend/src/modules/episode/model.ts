/**
 * Contrato del episodio clínico compartido por el registro clínico (paso 7)
 * y el traspaso (paso 8).
 *
 * Modelo: un audio = un evento clínico (`Encounter`), con varias entradas
 * (`ClinicalEntry`) por evento. Solo las entradas validadas alimentan el
 * registro, los datos de corte y los traspasos.
 *
 * Lo sirve el backend (`/-/api/episodes`) detrás de `EpisodeGateway`: cada paciente
 * asignado al usuario es un episodio y sus informes guardados son las atenciones.
 */

export type Discipline = "nursing" | "medicine" | "kinesiology";

export interface Professional {
  id: string;
  name: string;
  /** Rol visible, p. ej. «Enfermera clínica». */
  role: string;
  discipline: Discipline;
}

export interface Shift {
  id: string;
  label: string;
  startsAt: string;
  endsAt: string;
}

export interface Episode {
  /** Identificador estable del episodio: es la única llave de unión de los datos. */
  id: string;
  label: string;
  unit: string;
  admittedAt: string;
  /** Instante de corte del registro: nada posterior entra en él. */
  cutoffAt: string;
}

export type EntryKind = "assessment" | "vitals" | "intervention" | "plan";

export type EntryStatus = "validated" | "draft";

export interface Measurement {
  /** Código estable de la variable, p. ej. `spo2`. */
  code: string;
  label: string;
  value: string;
  unit: string;
}

export interface ClinicalEntry {
  id: string;
  kind: EntryKind;
  text: string;
  status: EntryStatus;
  measurements?: Measurement[];
}

export interface Encounter {
  id: string;
  episodeId: string;
  authorId: string;
  shiftId: string;
  /** Hora clínica de la atención (no la de carga del audio). */
  occurredAt: string;
  /** Origen del evento: un dictado de audio. */
  source: { type: "audio_dictation"; label: string };
  entries: ClinicalEntry[];
}

export type PendingStatus = "open" | "done";

export interface PendingTask {
  id: string;
  episodeId: string;
  title: string;
  status: PendingStatus;
  ownerId: string | null;
  dueAt: string | null;
  sourceEncounterId: string;
  closedAt?: string;
  closedById?: string;
}

export interface EpisodeRecord {
  episode: Episode;
  professionals: Professional[];
  shifts: Shift[];
  encounters: Encounter[];
  pendings: PendingTask[];
  openConflicts: OpenConflict[];
}

export interface OpenConflict {
  id: string;
  description: string;
  sourceEncounterIds: string[];
}

/** Filtro del registro: por profesional o por turno (ambos opcionales). */
export interface RecordFilter {
  professionalId?: string;
  shiftId?: string;
}

/** Dato vigente al corte, con su procedencia exacta. */
export interface CutoffDatum {
  code: string;
  label: string;
  value: string;
  unit: string;
  observedAt: string;
  source: Provenance;
}

export interface Provenance {
  encounterId: string;
  entryId: string;
  authorId: string;
}

/** Entrada validada copiada con su procedencia (para planes y cambios recientes). */
export interface SourcedEntry {
  entryId: string;
  encounterId: string;
  authorId: string;
  occurredAt: string;
  kind: EntryKind;
  text: string;
}

/**
 * Copia fija de lo comunicado en un traspaso. No referencia el estado vivo
 * del episodio: los pendientes guardan el estado que tenían al enviar.
 */
export interface HandoffSnapshot {
  episodeId: string;
  episodeLabel: string;
  cutoffAt: string;
  summaryText: string;
  recentChanges: SourcedEntry[];
  plan: SourcedEntry[];
  cutoffData: CutoffDatum[];
  pendings: PendingTask[];
  openConflicts?: OpenConflict[];
  /**
   * Última atención registrada al corte (validada o en borrador: la visita
   * ocurrió aunque su contenido siga reservado). Opcional porque los traspasos
   * guardados antes de este campo no lo traen.
   */
  lastEncounter?: LastEncounter | null;
}

export interface LastEncounter {
  encounterId: string;
  authorId: string;
  occurredAt: string;
}

export interface Handoff {
  id: string;
  fromId: string;
  toId: string;
  note: string;
  sentAt: string;
  snapshots: HandoffSnapshot[];
}

export interface SendHandoffInput {
  fromId: string;
  toId: string;
  note: string;
  /** Pacientes (episodios) que se entregan; los demás no se traspasan a esta persona. */
  episodeIds: string[];
}
