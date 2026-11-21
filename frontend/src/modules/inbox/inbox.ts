import type { InboxStatus, PatientWithCount } from "../patients/api";

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

/** Primero lo que requiere acción; dentro de cada grupo, por cama y luego por nombre. */
export function sortInbox(patients: readonly PatientWithCount[]): PatientWithCount[] {
  return [...patients].sort(
    (a, b) =>
      INBOX_STATUS[a.inboxStatus].rank - INBOX_STATUS[b.inboxStatus].rank ||
      a.bed.localeCompare(b.bed, "es", { numeric: true }) ||
      a.name.localeCompare(b.name, "es"),
  );
}

export function needsAction(status: InboxStatus): boolean {
  return status === "review" || status === "failed";
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
