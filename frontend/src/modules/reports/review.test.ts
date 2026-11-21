import { describe, expect, it } from "vitest";
import type { Report, ReviewItem } from "./api";
import { nextReviewItemId, pendingReviewItems, reviewTone } from "./review";

describe("revisión por excepción", () => {
  const a = item({ id: "a", severity: "high" });
  const b = item({ id: "b" });
  const c = item({ id: "c", kind: "clarification" });

  it("solo los puntos sin revisar, en el orden del backend", () => {
    const report = { reviewItems: [a, { ...b, reviewed: true }, c] } as Report;
    expect(pendingReviewItems(report).map((x) => x.id)).toEqual(["a", "c"]);
  });

  it("pasa directo al siguiente pendiente", () => {
    expect(nextReviewItemId([a, b, c], "a")).toBe("b");
    expect(nextReviewItemId([a, b, c], "b")).toBe("c");
    // Si el último se revisa primero, vuelve al primero pendiente.
    expect(nextReviewItemId([a, b, c], "c")).toBe("a");
    expect(nextReviewItemId([a], "a")).toBeUndefined();
  });

  it("rojo solo para conflictos de alto impacto con la evidencia", () => {
    expect(reviewTone(a)).toEqual({ color: "red", label: "Conflicto con evidencia · alto impacto" });
    expect(reviewTone(b).color).toBe("amber");
    expect(reviewTone({ ...c, severity: "high" })).toEqual({ color: "amber", label: "Aclaración" });
  });

  it("distingue un examen sin mención de un dato contradictorio", () => {
    expect(reviewTone({ ...b, alertKind: "omission" })).toEqual({ color: "amber", label: "Examen sin mención" });
  });

});

function item(overrides: Partial<ReviewItem>): ReviewItem {
  return {
    id: "x",
    kind: "evidence",
    severity: "medium",
    section: "examenes",
    message: "",
    itemIndex: null,
    alertKind: "value",
    evidenceId: null,
    evidenceTitle: "",
    evidenceTakenAt: null,
    reviewed: false,
    ...overrides,
  };
}
