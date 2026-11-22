import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { useReportDiff, type Report, type ReportDiff } from "./api";
import { diffRows } from "./diffRows";
import { ReportChangesSection, VersionChanges } from "./ReportChanges";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  useReportDiff: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({ Link: ({ children }: { children: ReactNode }) => <span>{children}</span> }));

const report = { id: "9", profession: "medico", patient: { id: 1, name: "P", identifier: "", bed: "" } } as Report;

it("muestra qué cambió respecto del informe anterior y su impacto en el registro oficial", () => {
  const diff: ReportDiff = {
    reportId: "9",
    previous: { id: "4", sequence: 1, authorName: "Dr. Rojas", recordedAt: "2026-11-19T10:00:00Z" },
    preview: false,
    officialVersion: 2,
    changes: [
      change("drogas_infusion:noradrenalina:dosis", "changed", "Noradrenalina", "dosis", "0.15 mcg/kg/min", "0.3 mcg/kg/min", "conflict"),
      change("dispositivos_invasivos:cvc", "removed", "CVC", "", "CVC · yugular", "", "still_in_record"),
      change("escalas:sofa:puntaje", "changed", "SOFA", "puntaje", "6", "8", "official_differs", "6"),
    ],
  };
  vi.mocked(useReportDiff).mockReturnValue({ data: diff, isPending: false, isError: false } as ReturnType<typeof useReportDiff>);

  render(<ReportChangesSection report={report} enabled />);
  fireEvent.click(screen.getByRole("button", { name: /Cambios desde el informe anterior/ }));

  expect(screen.getByText("1 en conflicto")).toBeInTheDocument();
  // Antes | después, lado a lado: el valor anterior a la izquierda, el nuevo a la derecha.
  const doseRow = "drogas_infusion|Noradrenalina";
  expect(within(screen.getByTestId(`before-${doseRow}`)).getByText("0.15 mcg/kg/min", { exact: false })).toBeInTheDocument();
  const after = screen.getByTestId(`after-${doseRow}`);
  expect(within(after).getByText("0.3 mcg/kg/min")).toBeInTheDocument();
  expect(within(after).getByText("En conflicto con el registro oficial")).toBeInTheDocument();
  const cvc = screen.getByTestId("after-dispositivos_invasivos:cvc");
  expect(within(cvc).getByText("No mencionado")).toBeInTheDocument();
  expect(within(cvc).getByText("Sigue vigente en el registro oficial")).toBeInTheDocument();
  expect(screen.getByText("El registro mantiene: 6")).toBeInTheDocument();
  expect(screen.getByText(/no significa suspendido/)).toBeInTheDocument();
});

it("agrupa en una fila los datos que cambian de un mismo elemento", () => {
  const rows = diffRows([
    change("medicamentos:ibuprofeno:dosis", "changed", "Ibuprofeno", "dosis", "10 mg", "5 mg"),
    change("medicamentos:ibuprofeno:hora", "changed", "Ibuprofeno", "hora", "22:07", "22:24"),
    change("medicamentos:meropenem", "added", "Meropenem", "", "", "Meropenem · 1 g"),
    change("evaluacion_motora::tolerancia", "added", "", "tolerancia", "", "Buena"),
    change("evaluacion_motora::nivel", "added", "", "nivel", "", "En cama"),
  ]);

  expect(rows.map((row) => [row.kind, row.title, row.lines.length])).toEqual([
    ["changed", "Ibuprofeno", 2],
    ["added", "", 1],
    // Datos que antes no estaban: son nuevos, no cambios.
    ["added", "", 2],
  ]);
});

it("una versión que solo agrega información lo dice y no muestra la columna «antes»", () => {
  render(<VersionChanges changes={[change("pendientes:eco", "added", "Eco", "", "", "Ecocardiograma")]} />);

  fireEvent.click(screen.getByRole("button", { name: "Ver cambios (1 nuevo)" }));

  expect(screen.getByText(/Solo hay información nueva/)).toBeInTheDocument();
  expect(screen.queryByText("Versión anterior")).not.toBeInTheDocument();
});

it("en una versión oficial lo ausente se muestra como retirado", () => {
  render(<VersionChanges changes={[change("medicamentos:amoxicilina", "removed", "Amoxicilina", "", "Amoxicilina", "")]} />);

  fireEvent.click(screen.getByRole("button", { name: "Ver cambios (1 retirado)" }));

  expect(screen.getByText("Retirado")).toBeInTheDocument();
});

function change(
  key: string,
  kind: ReportDiff["changes"][number]["kind"],
  item: string,
  field: string,
  before: string,
  after: string,
  impact: ReportDiff["changes"][number]["impact"] = null,
  officialValue = "",
): ReportDiff["changes"][number] {
  return { key, section: key.split(/:|#/)[0], sectionTitle: "", kind, item, field, before, after, impact, officialValue };
}
