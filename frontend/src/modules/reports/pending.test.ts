import { describe, expect, it } from "vitest";
import { pendingFields, pendingSections } from "./pending";

describe("pending information", () => {
  it("lists the empty leaf fields with readable names", () => {
    expect(pendingFields({ pvc: null, pam: 76, evidencia: null })).toEqual(["Pvc"]);
  });

  it("marks several items of a list by number", () => {
    expect(pendingFields([{ dosis: 1 }, { dosis: null }], "Drogas")).toEqual(["Drogas n.º 2 › Dosis"]);
  });

  it("reports sections without any information and sections with gaps, in template order", () => {
    const data = {
      metadatos: { cama: null },
      alergias: [],
      escalas: [{ nombre: "SOFA", puntaje: null }],
      resumen: "Estable",
    };

    const pending = pendingSections(data, ["metadatos", "resumen", "escalas", "alergias"]);

    expect(pending).toEqual([
      { key: "escalas", fields: ["Puntaje"] },
      { key: "alergias", fields: ["Sin información"] },
    ]);
  });
});
