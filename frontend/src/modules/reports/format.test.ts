import { describe, expect, it } from "vitest";
import { reportOrdinal, reportTitle } from "./format";

describe("report ordinals", () => {
  it("names the first reports of a category", () => {
    expect(reportOrdinal(1)).toBe("Primer informe");
    expect(reportOrdinal(2)).toBe("Segundo informe");
    expect(reportOrdinal(3)).toBe("Tercer informe");
  });

  it("falls back to a number past the tenth", () => {
    expect(reportOrdinal(12)).toBe("Informe n.º 12");
  });

  it("includes the professional category", () => {
    expect(reportTitle(2, "kinesiologia")).toBe("Segundo informe de Kinesiología");
  });
});
