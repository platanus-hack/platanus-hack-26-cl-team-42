import type { Report, ReviewItem } from "./api";

// Revisión por excepción: el autor solo revisa los puntos pendientes que entrega el backend
// (conflictos con la evidencia y aclaraciones concretas), del más grave al más leve.

export type ReviewColor = "red" | "amber";

/** Los puntos aún por revisar, en el orden del backend (severidad alta primero). */
export function pendingReviewItems(report: Report): ReviewItem[] {
  return report.reviewItems.filter((item) => !item.reviewed);
}

/** El punto siguiente tras revisar `currentId` (el que le sigue o, si era el último, el primero). */
export function nextReviewItemId(pending: ReviewItem[], currentId: string): string | undefined {
  const index = pending.findIndex((item) => item.id === currentId);
  const rest = pending.filter((item) => item.id !== currentId);
  if (rest.length === 0) return undefined;
  return (index >= 0 ? rest[index] : undefined)?.id ?? rest[0].id;
}

/** Texto y color de un punto: rojo solo para conflictos de alto impacto con la evidencia. */
export function reviewTone(item: ReviewItem): { color: ReviewColor; label: string } {
  if (item.kind === "evidence") {
    if (item.alertKind === "omission") return { color: "amber", label: "Examen sin mención" };
    return item.severity === "high"
      ? { color: "red", label: "Conflicto con evidencia · alto impacto" }
      : { color: "amber", label: "Discrepancia con evidencia" };
  }
  return { color: "amber", label: "Aclaración" };
}
