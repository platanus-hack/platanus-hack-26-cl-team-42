import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useTemplate, type TemplateDetail } from "../templates/api";
import { useEditReportItem, useReviewItem, useValidateReport, type Report, type ReviewItem } from "./api";
import { ReportView } from "./ReportView";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  useEditReportItem: vi.fn(),
  useReviewItem: vi.fn(),
  useValidateReport: vi.fn(),
  useReportDiff: () => ({ data: undefined, isPending: true, isError: false }),
}));
vi.mock("../templates/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../templates/api")>()),
  useTemplate: vi.fn(),
  useComplementSection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@tanstack/react-router", () => ({ Link: ({ children }: { children: ReactNode }) => <span>{children}</span> }));

const reviewMutate = vi.fn();
const saveMutate = vi.fn();
const editMutate = vi.fn();

beforeEach(() => {
  reviewMutate.mockReset();
  saveMutate.mockReset();
  editMutate.mockReset();
  vi.mocked(useTemplate).mockReturnValue({ data: undefined } as ReturnType<typeof useTemplate>);
  vi.mocked(useEditReportItem).mockReturnValue({
    mutate: editMutate, reset: vi.fn(), isPending: false, isError: false,
  } as unknown as ReturnType<typeof useEditReportItem>);
  vi.mocked(useReviewItem).mockReturnValue({ mutate: reviewMutate, isPending: false, isError: false } as unknown as ReturnType<
    typeof useReviewItem
  >);
  vi.mocked(useValidateReport).mockReturnValue({ mutate: saveMutate, isPending: false, isError: false } as unknown as ReturnType<
    typeof useValidateReport
  >);
});

afterEach(() => vi.unstubAllGlobals());

it("empieza en el punto más grave y «Validar y continuar» lo revisa desde el encabezado", () => {
  const { rerender } = render(<ReportView report={report([conflict, clarification])} />);

  expect(screen.getByText("2 puntos por revisar")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Guardar informe" })).not.toBeInTheDocument();
  const topics = screen.getByRole("group", { name: "Temas del informe" });
  expect(within(topics).getByRole("button", { name: "Exámenes y cultivos · Alerta", pressed: true })).toBeInTheDocument();
  expect(within(topics).getByRole("button", { name: "Tratamiento · Por revisar", pressed: false })).toBeInTheDocument();
  const point = screen.getByRole("region", { name: "Punto por revisar" });
  expect(within(point).getByText("Conflicto con evidencia · alto impacto")).toBeInTheDocument();
  expect(within(point).getByText(/Lactato 2.1.*4.8/)).toBeInTheDocument();
  expect(within(point).getByText(/Gases/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Validar y continuar" }));

  expect(reviewMutate).toHaveBeenCalledWith({ reportId: "7", itemId: conflict.id }, expect.anything());
  rerender(<ReportView report={report([{ ...conflict, reviewed: true }, clarification])} />);
  act(() => reviewMutate.mock.calls[0][1].onSuccess());

  expect(screen.getByText("1 punto por revisar")).toBeInTheDocument();
  expect(within(point).getByText("Aclaración")).toBeInTheDocument();
  expect(within(topics).getByRole("button", { name: "Tratamiento · Por revisar", pressed: true })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Guardar informe" })).not.toBeInTheDocument();
});

it("puedes seleccionar cualquier tema y volver a los puntos pendientes desde el encabezado", () => {
  render(<ReportView report={report([conflict])} />);

  const topics = screen.getByRole("group", { name: "Temas del informe" });
  fireEvent.click(within(topics).getByRole("button", { name: "Tratamiento" }));
  expect(within(topics).getByRole("button", { name: "Tratamiento", pressed: true })).toBeInTheDocument();
  expect(screen.getByText("furosemida")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Punto por revisar" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Ir al siguiente pendiente" }));
  expect(within(topics).getByRole("button", { name: "Exámenes y cultivos · Alerta", pressed: true })).toBeInTheDocument();
  expect(reviewMutate).not.toHaveBeenCalled();
});

it("sin puntos pendientes ofrece guardar (publicar y cerrar) y no hay recorrido por temas", () => {
  render(<ReportView report={report([{ ...conflict, reviewed: true }])} />);

  expect(screen.queryByRole("button", { name: "Validar y continuar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Punto por revisar" })).not.toBeInTheDocument();
  expect(screen.getByText(/lo publica al equipo del paciente y lo cierra/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Guardar informe" }));
  expect(saveMutate).toHaveBeenCalledWith("7");
});

it("familia y observaciones se pueden leer en el informe guardado sin ser una categoría de revisión", () => {
  const { rerender } = render(<ReportView report={report([])} />);
  const topics = screen.getByRole("group", { name: "Temas del informe" });
  expect(within(topics).queryByRole("button", { name: /Familia y observaciones|Guardar/ })).not.toBeInTheDocument();

  rerender(<ReportView report={{ ...report([]), status: "done", canEdit: false }} />);
  expect(screen.getByText("Se informa a la hija.")).toBeInTheDocument();
});

it("edita el ítem seleccionado con los campos de la plantilla", () => {
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  });
  const draft = report([]);
  const alert = { descripcion: "Hiperglicemia", severidad: null, evidencia: "Cita original" };
  draft.data = { alertas: [{ ...alert, descripcion: "Primera alerta" }, alert] };
  draft.topics = [{ id: "alerts", label: "Alertas y alergias", sections: ["alertas"] }];
  draft.noteSections = [];
  const template: TemplateDetail = {
    slug: "medico_uci", name: "Médico UCI", description: "", profession: "medico", version: 1,
    output_schema: {
      required: ["alertas"],
      properties: { alertas: { type: "array", items: { $ref: "#/$defs/Alerta" } } },
      $defs: { Alerta: {
        type: "object",
        properties: {
          descripcion: { type: "string" },
          severidad: { type: ["string", "null"], enum: ["alta", null] },
          evidencia: { type: ["string", "null"] },
        },
      } },
    },
  };
  vi.mocked(useTemplate).mockReturnValue({ data: template } as ReturnType<typeof useTemplate>);
  render(<ReportView report={draft} />);

  expect(screen.getByRole("button", { name: "Editar Alertas · ítem 1" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Editar Alertas · ítem 2" }));
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByRole("textbox", { name: "Descripcion" })).toHaveValue("Hiperglicemia");
  expect(dialog.getByRole("combobox", { name: "Severidad" })).toHaveTextContent("Sin informar");
  expect(dialog.getByText("Cita del dictado · Cita original")).toBeInTheDocument();

  fireEvent.change(dialog.getByRole("textbox", { name: "Descripcion" }), { target: { value: "Glicemia elevada" } });
  fireEvent.click(dialog.getByRole("button", { name: "Guardar cambios" }));
  expect(editMutate).toHaveBeenCalledWith({
    reportId: draft.id, section: "alertas", index: 1, revision: draft.editRevision,
    value: { ...alert, descripcion: "Glicemia elevada" },
  }, expect.anything());
});

const conflict: ReviewItem = {
  id: "value:examenes:lactato",
  kind: "evidence",
  severity: "high",
  section: "examenes",
  message: "El informe registra Lactato 2.1 mmol/L, pero el examen informa 4.8 mmol/L.",
  itemIndex: 0,
  alertKind: "value",
  evidenceId: 3,
  evidenceTitle: "Gases y química",
  evidenceTakenAt: "2026-11-21T08:00:00Z",
  reviewed: false,
};

const clarification: ReviewItem = {
  ...conflict,
  id: "clarification:medicamentos:0:unidad",
  kind: "clarification",
  severity: "medium",
  section: "medicamentos",
  message: "furosemida: se dictó la dosis 20 sin unidad (mg, g, UI…).",
  alertKind: null,
  evidenceId: null,
  evidenceTitle: "",
  evidenceTakenAt: null,
};

function report(reviewItems: ReviewItem[]): Report {
  return {
    id: "7",
    extractionId: "1",
    recordingId: "1",
    templateSlug: "medico_uci",
    templateName: "Médico UCI",
    templateVersion: 1,
    status: "review",
    profession: "medico",
    patientReference: "",
    patient: { id: 1, name: "Paciente", identifier: "", bed: "" },
    authorName: "Dr. Rojas",
    authorEmail: "",
    sequence: 1,
    data: {
      examenes: [{ examen: "Lactato", valor: 2.1, unidad: "mmol/L" }],
      medicamentos: [{ nombre: "furosemida", dosis: 20, unidad: null }],
      comunicacion_familia: "Se informa a la hija.",
    },
    homologations: [],
    error: "",
    extractionStatus: "done",
    consolidation: "pending",
    validatedAt: null,
    topics: [
      { id: "treatment", label: "Tratamiento", sections: ["medicamentos"] },
      { id: "exams", label: "Exámenes y cultivos", sections: ["examenes"] },
    ],
    noteSections: ["comunicacion_familia"],
    reviewItems,
    evidenceAlerts: [],
    canEdit: true,
    editRevision: "r1",
    recordedAt: "2026-11-21T09:00:00Z",
    created_at: "2026-11-21T09:00:00Z",
    updated_at: "2026-11-21T09:00:00Z",
  };
}
