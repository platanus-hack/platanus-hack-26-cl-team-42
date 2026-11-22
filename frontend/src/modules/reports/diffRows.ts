import type { ChangeImpact, RecordChange, ReportChange } from "./api";

/** Una fila de la comparación: un elemento (o los datos sueltos de una sección) antes y después. */
export interface DiffRow {
  key: string;
  section: string;
  /** `added`/`removed`: el elemento entero aparece o deja de aparecer · `changed`: cambian sus datos. */
  kind: "added" | "removed" | "changed";
  title: string;
  lines: DiffLine[];
}

export interface DiffLine {
  key: string;
  label: string;
  before: string;
  after: string;
  impact: ChangeImpact | null;
  officialValue: string;
}

/**
 * Agrupa los cambios en filas: los datos de un mismo elemento van juntos. Una fila es `added` si
 * nada de ella tenía valor antes; `changed` si al menos un dato cambió de valor.
 */
export function diffRows(changes: (RecordChange | ReportChange)[]): DiffRow[] {
  const rows: DiffRow[] = [];
  const byItem = new Map<string, DiffRow>();
  for (const change of changes) {
    const line: DiffLine = {
      key: change.key,
      label: change.field,
      before: change.before,
      after: change.after,
      impact: "impact" in change ? change.impact : null,
      officialValue: "officialValue" in change ? change.officialValue : "",
    };
    // Un elemento entero (o un texto) que aparece o deja de aparecer va en su propia fila.
    if ((change.kind === "added" || change.kind === "removed") && !change.field) {
      rows.push({ key: change.key, section: change.section, kind: change.kind, title: "", lines: [line] });
      continue;
    }
    const groupKey = `${change.section}|${change.item}`;
    let row = byItem.get(groupKey);
    if (!row) {
      row = { key: groupKey, section: change.section, kind: "added", title: change.item, lines: [] };
      byItem.set(groupKey, row);
      rows.push(row);
    }
    row.lines.push(line);
    if (line.before) row.kind = "changed";
  }
  return rows;
}
