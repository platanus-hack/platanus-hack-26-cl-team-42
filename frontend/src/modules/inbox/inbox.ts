import { PROCESSING_STEPS, type PatientWithCount } from "../patients/api";

// Reglas de la bandeja «Mis pacientes»: orden de la lista y señales de cada paciente.

/** Nivel de atención: define el color de la fila. */
export type InboxTier = "urgent" | "review" | "processing" | "ok" | "no_data";

export type TierColor = "red" | "amber" | "green" | "gray";

interface InboxTierMeta {
  /** Rojo: urgencia clínica; ámbar: gestión pendiente; verde: al día; gris: sin datos o en proceso. */
  color: TierColor;
  /** Insignia cuando el paciente no tiene ninguna señal propia. */
  badge: string;
}

const INBOX_TIERS: Record<InboxTier, InboxTierMeta> = {
  urgent: { color: "red", badge: "Urgente" },
  review: { color: "amber", badge: "Por revisar" },
  processing: { color: "gray", badge: "Procesando" },
  ok: { color: "green", badge: "Al día" },
  no_data: { color: "gray", badge: "Sin datos" },
};

/** Una señal del paciente; la primera define la insignia y las siguientes van en el subtítulo. */
export interface InboxSignal {
  text: string;
  color: TierColor;
  processing?: boolean;
}

export interface InboxRowState {
  tier: InboxTier;
  color: TierColor;
  badge: InboxSignal;
  /** Hasta dos señales más (o, si no hay, lo informativo), para el subtítulo. */
  secondary: string[];
}

/** El nivel de un paciente: primero la urgencia clínica, luego lo que te toca gestionar. */
export function inboxTier(patient: PatientWithCount): InboxTier {
  if (patient.criticality === "critical" || patient.visitPriority === "now") return "urgent";
  if (
    patient.inboxStatus === "review" ||
    patient.inboxStatus === "failed" ||
    patient.myOpenConflicts > 0 ||
    patient.visitPriority === "soon" ||
    patient.criticality === "high"
  ) {
    return "review";
  }
  if (patient.inboxStatus === "processing") return "processing";
  if (patient.criticality === "unknown") return "no_data";
  return "ok";
}

/**
 * Cómo se ve la fila: el color lo pone el nivel y la insignia, la señal más importante. Una segunda
 * señal (p. ej. «Por validar» en un paciente crítico) no se pierde: pasa al subtítulo.
 */
export function inboxRowState(patient: PatientWithCount, now: Date = new Date()): InboxRowState {
  const tier = inboxTier(patient);
  const { color, badge } = INBOX_TIERS[tier];
  const [first, ...rest] = signalsOf(patient);
  const secondary = rest.slice(0, 2).map((signal) => signal.text);
  if (secondary.length === 0) secondary.push(...contextOf(patient, tier, now));
  return { tier, color, badge: first ?? { text: badge, color }, secondary };
}

/** Orden por cama y nombre, con los pacientes sin cama al final. */
export function sortInbox(patients: readonly PatientWithCount[]): PatientWithCount[] {
  return [...patients].sort((a, b) => {
    const firstBed = a.bed.trim();
    const secondBed = b.bed.trim();
    return Number(!firstBed) - Number(!secondBed) ||
      firstBed.localeCompare(secondBed, "es", { numeric: true }) ||
      a.name.localeCompare(b.name, "es") ||
      a.id - b.id;
  });
}

/** Busca por nombre y cama, sin distinguir mayúsculas ni tildes y conservando el orden. */
export function filterInbox(patients: readonly PatientWithCount[], query: string): readonly PatientWithCount[] {
  const terms = normalizeSearch(query).trim().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return patients;

  return patients.filter(({ name, bed }) => {
    const searchable = normalizeSearch(`${name} ${bed}`);
    return terms.every((term) => searchable.includes(term));
  });
}

function normalizeSearch(value: string): string {
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es");
}

/** «53 min», «2 h»… o «Sin visitas» si ningún profesional lo ha visto aún. */
export function formatLastVisit(iso: string | null, now: Date = new Date()): string {
  return iso ? formatSince(iso, now) : "Sin visitas";
}

/** Hace cuánto fue el último dictado, en formato corto: «15 min», «2 h», «ayer», «3 d». */
export function formatSince(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Sin dictados";
  const minutes = Math.max(0, Math.round((now.getTime() - Date.parse(iso)) / 60_000));
  if (minutes < 1) return "Ahora";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Ayer" : `${days} d`;
}

/** Todas las señales que aplican, de la más a la menos importante. */
function signalsOf(patient: PatientWithCount): InboxSignal[] {
  const signals: (InboxSignal | false)[] = [
    patient.criticality === "critical" && { text: "Crítico", color: "red" },
    patient.visitPriority === "now" && { text: patient.visitPriorityLabel || "Visitar ahora", color: "red" },
    patient.inboxStatus === "failed" && { text: "Error al procesar", color: "amber" },
    patient.inboxStatus === "review" && { text: "Por validar", color: "amber" },
    patient.myOpenConflicts > 0 && {
      text: patient.myOpenConflicts === 1 ? "1 conflicto tuyo" : `${patient.myOpenConflicts} conflictos tuyos`,
      color: "amber",
    },
    patient.visitPriority === "soon" && { text: patient.visitPriorityLabel || "Visitar pronto", color: "amber" },
    patient.criticality === "high" && { text: "Criticidad alta", color: "amber" },
    patient.inboxStatus === "processing" && {
      text: patient.processingLabel ? `${patient.processingLabel} ${patient.processingStep ?? 0}/${PROCESSING_STEPS}` : "Procesando…",
      color: "gray",
      processing: true,
    },
  ];
  return signals.filter((signal): signal is InboxSignal => signal !== false);
}

/** Lo informativo, para el subtítulo de un paciente sin otras señales. */
function contextOf(patient: PatientWithCount, tier: InboxTier, now: Date): string[] {
  if (tier === "no_data") return ["Sin informe oficial"];
  const visit = patient.lastDictationAt ? `Última visita ${formatSince(patient.lastDictationAt, now)}` : "Sin visitas";
  const tasks = patient.pendingTasks > 0 ? `${patient.pendingTasks} ${patient.pendingTasks === 1 ? "pendiente" : "pendientes"}` : null;
  const criticality = patient.criticality !== "unknown" && patient.criticality !== "critical" && patient.criticality !== "high"
    ? patient.criticalityLabel
    : null;
  return [criticality, visit, tasks].filter((item): item is string => item !== null).slice(0, 2);
}
