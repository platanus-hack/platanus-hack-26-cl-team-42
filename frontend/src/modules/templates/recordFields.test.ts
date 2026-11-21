import { describe, expect, it } from "vitest";
import { countFields, isEmptyValue, sectionLabel, sectionState } from "./recordFields";

describe("isEmptyValue", () => {
  it("treats null, empty text, lists and objects as pending", () => {
    for (const value of [null, undefined, "", [], {}]) expect(isEmptyValue(value)).toBe(true);
  });

  it("keeps false and zero as real information", () => {
    for (const value of [false, 0, "x", [0], { a: null }]) expect(isEmptyValue(value)).toBe(false);
  });
});

describe("countFields", () => {
  it("counts filled and pending leaves recursively", () => {
    const value = { cama: "7", turno: null, items: [{ ml: 40, tipo: "drenaje" }, { ml: null, tipo: "" }] };
    expect(countFields(value)).toEqual({ filled: 3, pending: 3 });
  });

  it("counts an empty list as a single pending field", () => {
    expect(countFields([])).toEqual({ filled: 0, pending: 1 });
  });
});

describe("sectionState", () => {
  it("waits for sections the model has not reached while it is working", () => {
    expect(sectionState(false, undefined, true)).toBe("waiting");
    expect(sectionState(true, null, true)).toBe("waiting");
  });

  it("marks sections without information as pending once extraction is over", () => {
    expect(sectionState(false, undefined, false)).toBe("pending");
    expect(sectionState(true, [], false)).toBe("pending");
  });

  it("tells partial from complete sections", () => {
    expect(sectionState(true, { a: 1, b: null }, false)).toBe("partial");
    expect(sectionState(true, { a: 1, b: [2] }, false)).toBe("complete");
  });
});

describe("sectionLabel", () => {
  it("turns keys into readable titles", () => {
    expect(sectionLabel("control_hemodinamico")).toBe("Control hemodinamico");
  });
});
