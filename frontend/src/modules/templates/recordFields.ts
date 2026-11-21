// Qué partes de un registro extraído tienen información y cuáles siguen pendientes.

export interface FieldCount {
  filled: number;
  pending: number;
}

/** Un valor vacío (null, texto vacío, lista u objeto sin contenido) es información pendiente. */
export function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

/** Cuenta los campos hoja con y sin información dentro de un valor del registro. */
export function countFields(value: unknown): FieldCount {
  if (isEmptyValue(value)) return { filled: 0, pending: 1 };
  if (Array.isArray(value)) return sum(value.map(countFields));
  if (typeof value === "object") return sum(Object.values(value as Record<string, unknown>).map(countFields));
  return { filled: 1, pending: 0 };
}

export type SectionState = "waiting" | "pending" | "partial" | "complete";

/**
 * - `waiting`: el modelo todavía no llega a esta sección.
 * - `pending`: sin ninguna información.
 * - `partial`: con información y campos aún pendientes.
 * - `complete`: sin campos pendientes.
 */
export function sectionState(present: boolean, value: unknown, inProgress: boolean): SectionState {
  if (!present) return inProgress ? "waiting" : "pending";
  const { filled, pending } = countFields(value);
  if (filled === 0) return inProgress ? "waiting" : "pending";
  return pending === 0 ? "complete" : "partial";
}

/** `control_hemodinamico` → `Control hemodinamico`. */
export function sectionLabel(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function sum(counts: FieldCount[]): FieldCount {
  return counts.reduce((total, count) => ({ filled: total.filled + count.filled, pending: total.pending + count.pending }), {
    filled: 0,
    pending: 0,
  });
}
