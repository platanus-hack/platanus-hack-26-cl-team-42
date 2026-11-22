import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { usePatientOverview, usePatientSummary, type Highlight, type PatientSummary } from "../patients/api";
import { PatientSummaryView, type PatientTab } from "./PatientSummaryView";

vi.mock("../patients/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../patients/api")>()),
  usePatientSummary: vi.fn(),
  usePatientOverview: vi.fn(),
}));

vi.mock("../reconciliation/api", () => ({ useReconciliations: () => ({ data: [] }) }));
vi.mock("../panel/api", () => ({
  isRunning: () => false,
  usePanels: () => ({ data: [] }),
  useOpenPanel: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));
vi.mock("@tanstack/react-router", () => ({ Link: ({ children }: { children: ReactNode }) => <span>{children}</span> }));

it("muestra indicaciones y plan en secciones separadas de una misma pestaña", () => {
  const onTabChange = vi.fn();
  const summary: PatientSummary = {
    patient: { id: 1, name: "Paciente", identifier: "", bed: "" },
    reportCount: 1,
    version: 1,
    versionReason: "official",
    status: "",
    brief: "Evolución estable.",
    synthesisPending: false,
    criticality: { level: "stable", label: "Estable", reasons: [] },
    keyPoints: [],
    treatmentPending: [
      entry("Indicaciones", "indicaciones", "Control de saturación ahora"),
      entry("Pendientes", "pendientes", "Radiografía de control"),
      entry("Metas del día", "metas_del_dia", "Sentarse al borde de la cama hoy"),
      entry("Metas del día", "objetivos_terapeuticos", "Recuperar marcha independiente"),
      entry("Recomendaciones", "recomendaciones_equipo", "Continuar rehabilitación ambulatoria"),
    ],
    abnormal: [],
    byProfession: [],
    highlights: [],
  };
  vi.mocked(usePatientSummary).mockReturnValue({ data: summary } as ReturnType<typeof usePatientSummary>);
  vi.mocked(usePatientOverview).mockReturnValue({ data: undefined, isPending: true } as ReturnType<typeof usePatientOverview>);

  const view = (tab: PatientTab) => (
    <PatientSummaryView patientId={1} reports={[]} onOpenReport={vi.fn()} tab={tab} onTabChange={onTabChange} />
  );
  const { rerender } = render(view("summary"));

  expect(screen.getByText("Evolución estable.")).toBeInTheDocument();
  expect(screen.queryByText("Control de saturación ahora")).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Indicaciones y plan.*5 registros/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ver plan e indicaciones" }));
  expect(onTabChange).toHaveBeenCalledWith("plan");

  rerender(view("plan"));
  const orders = screen.getByRole("region", { name: "Indicaciones" });
  const plan = screen.getByRole("region", { name: "Plan" });
  expect(orders).toHaveTextContent(/Corto plazo.*Control de saturación ahora.*Radiografía de control.*Sentarse al borde de la cama hoy/);
  expect(orders).not.toHaveTextContent("Recuperar marcha independiente");
  expect(plan).toHaveTextContent(/Mediano y largo plazo.*Recuperar marcha independiente.*Continuar rehabilitación ambulatoria/);
  expect(plan).not.toHaveTextContent("Sentarse al borde de la cama hoy");
});

function entry(group: string, section: string, text: string): Highlight {
  return { group, section, text, reportId: "1", profession: "medico", authorName: "", at: "", severity: "" };
}
