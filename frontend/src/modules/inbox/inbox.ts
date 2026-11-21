import type { InboxStatus, PatientCriticality, PatientWithCount, VisitPriority } from "../patients/api";

// Reglas de la bandeja «Mis pacientes»: orden y cómo se nombra cada estado.

interface InboxStatusMeta {
  label: string;
  /** Solo lo que requiere acción lleva color. */
  color: "red" | "amber" | "gray" | undefined;
  /** Prioridad en la bandeja: menor va primero. */
  rank: number;
}

export const INBOX_STATUS: Record<InboxStatus, InboxStatusMeta> = {
  review: { label: "Por validar", color: "amber", rank: 0 },
  failed: { label: "Error al procesar", color: "red", rank: 1 },
  processing: { label: "Procesando…", color: "gray", rank: 2 },
  up_to_date: { label: "Al día", color: undefined, rank: 3 },
};

export const CRITICALITY_META: Record<PatientCriticality, { color: "red" | "orange" | "amber" | "green" | "gray" }> = {
  critical: { color: "red" },
  high: { color: "orange" },
  moderate: { color: "amber" },
  stable: { color: "green" },
  unknown: { color: "gray" },
};

export const VISIT_META: Record<VisitPriority, { color: "red" | "amber" | "gray"; bold: boolean }> = {
  now: { color: "red", bold: true },
  soon: { color: "amber", bold: true },
  ok: { color: "gray", bold: false },
  unknown: { color: "gray", bold: false },
};

/**
 * Primero lo que requiere acción; dentro de cada grupo, los pacientes con conflictos tuyos por
 * resolver, luego lo más urgente de visitar (criticidad y tiempo sin verlo) y, a igualdad, por
 * cama y luego por nombre.
 */
export function sortInbox(patients: readonly PatientWithCount[]): PatientWithCount[] {
  return [...patients].sort(
    (a, b) =>
      INBOX_STATUS[a.inboxStatus].rank - INBOX_STATUS[b.inboxStatus].rank ||
      b.myOpenConflicts - a.myOpenConflicts ||
      b.priorityScore - a.priorityScore ||
      a.bed.localeCompare(b.bed, "es", { numeric: true }) ||
      a.name.localeCompare(b.name, "es"),
  );
}

export function needsAction(status: InboxStatus): boolean {
  return status === "review" || status === "failed";
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
