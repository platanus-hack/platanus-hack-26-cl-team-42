import { sectionLabel } from "../templates/recordFields";

// Qué información quedó pendiente en un informe (campos vacíos del registro).

export interface PendingSection {
  key: string;
  /** Nombres legibles de los campos sin información. */
  fields: string[];
}

const IGNORED_KEYS = new Set(["evidencia"]);

/** Los campos hoja vacíos de un valor del registro, con su nombre legible. */
export function pendingFields(value: unknown, label = ""): string[] {
  if (value === null || value === undefined || value === "") return [label];
  if (Array.isArray(value)) {
    if (value.length === 0) return [label];
    return value.flatMap((item, index) => pendingFields(item, value.length > 1 ? `${label} n.º ${index + 1}` : label));
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([key]) => !IGNORED_KEYS.has(key));
    if (entries.length === 0) return [label];
    return entries.flatMap(([key, child]) => pendingFields(child, joinLabel(label, sectionLabel(key))));
  }
  return [];
}

/** Secciones del informe con información pendiente, en el orden de la plantilla. */
export function pendingSections(data: Record<string, unknown>, order: string[]): PendingSection[] {
  const keys = order.length > 0 ? order : Object.keys(data);
  const sections: PendingSection[] = [];
  for (const key of keys) {
    if (key === "metadatos") continue;
    const value = data[key];
    const fields = isEmptySection(value) ? ["Sin información"] : pendingFields(value).filter((field) => field !== "");
    if (fields.length > 0) sections.push({ key, fields });
  }
  return sections;
}

function isEmptySection(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0)
  );
}

function joinLabel(parent: string, child: string): string {
  return parent ? `${parent} › ${child}` : child;
}
