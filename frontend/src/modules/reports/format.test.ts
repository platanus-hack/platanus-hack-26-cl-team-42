import { describe, expect, it } from "vitest";
import { anonymizeNames, reportOrdinal, reportTitle } from "./format";

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

describe("anonymizeNames", () => {
  const people = [
    { name: "Dr. Rojas", profession: "medico" },
    { name: "EU Soto", profession: "enfermeria" },
  ];

  it("replaces a name and its role in parentheses with just the role", () => {
    const text = "Dr. Rojas (Médico UCI) registró «0.15» y EU Soto (Enfermería) registró «0.3».";
    expect(anonymizeNames(text, people)).toBe("Médico UCI registró «0.15» y Enfermería registró «0.3».");
  });

  it("handles nested parentheses and bare names", () => {
    const text = "(registrado por EU Soto (Enfermería)) y confirmado por Dr. Rojas.";
    expect(anonymizeNames(text, people)).toBe("(registrado por Enfermería) y confirmado por Médico UCI.");
  });

  it("leaves the text alone when there are no names to hide", () => {
    expect(anonymizeNames("Sin nombres.", [{ name: "", profession: "medico" }])).toBe("Sin nombres.");
  });

  it("does not trip over regex characters in names", () => {
    expect(anonymizeNames("Klgo. (Muñoz) opinó", [{ name: "Klgo. (Muñoz)", profession: "kinesiologia" }])).toBe(
      "Kinesiología opinó",
    );
  });
});
