import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AgentCouncil } from "./AgentCouncil";
import { usePanels, useOpenPanel, type Panel } from "./api";

const mutate = vi.fn();

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  usePanels: vi.fn(),
  useOpenPanel: vi.fn(),
}));

const done: Panel = {
  id: "1",
  status: "done",
  patientId: 5,
  patientName: "Clemente Vial",
  conflictId: "9",
  question: "¿Qué postura es la más segura?",
  participants: ["Tomás Werth · Médico UCI", "Cristóbal Tubino · Kinesiología"],
  turns: [
    { round: 1, profession: "medico", role: "Médico UCI", author: "Tomás Werth · Médico UCI", stance: "RASS -4", body: "Mantener sedación." },
    { round: 2, profession: "medico", role: "Médico UCI", author: "Tomás Werth · Médico UCI", stance: "Reevaluar", body: "Reevaluar junto a kinesiología." },
  ],
  recommendation: {
    resumen: "Hay que reevaluar el RASS.",
    recomendacion: "Reevaluar el RASS al lado de la cama y registrar un único valor.",
    acuerdos: ["Tratar con cautela"],
    desacuerdos: [],
    siguientes_pasos: ["Revisar la hoja de enfermería"],
    confianza: "media",
    aviso: "Sugerencia generada por agentes.",
  },
  error: "",
  created_at: "2026-11-21T10:00:00Z",
  finished_at: "2026-11-21T10:01:00Z",
};

beforeEach(() => {
  mutate.mockReset();
  vi.mocked(useOpenPanel).mockReturnValue({ mutate, isPending: false, isError: false } as unknown as ReturnType<typeof useOpenPanel>);
});

function panels(data: Panel[]) {
  vi.mocked(usePanels).mockReturnValue({ data } as ReturnType<typeof usePanels>);
}

it("desde un conflicto lanza la consulta sin exigir pregunta", () => {
  panels([]);
  render(<AgentCouncil conflictId="9" patientId={5} canLaunch />);

  fireEvent.click(screen.getByRole("button", { name: "Consultar al consejo de agentes" }));

  expect(mutate).toHaveBeenCalledWith({ conflictId: "9", patientId: 5, question: "", areas: [] }, expect.anything());
});

it("una pregunta libre necesita texto", () => {
  panels([]);
  render(<AgentCouncil patientId={5} canLaunch />);
  const button = screen.getByRole("button", { name: "Consultar al consejo de agentes" });

  expect(button).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText("Tu pregunta médica sobre este paciente"), { target: { value: "¿Cambiar antibiótico?" } });
  expect(button).toBeEnabled();
  fireEvent.click(button);

  expect(mutate).toHaveBeenCalledWith(
    { conflictId: undefined, patientId: 5, question: "¿Cambiar antibiótico?", areas: [] },
    expect.anything(),
  );
});

it("una pregunta libre puede elegir las áreas que opinan", () => {
  panels([]);
  render(<AgentCouncil patientId={5} canLaunch />);

  fireEvent.click(screen.getByRole("checkbox", { name: "Nutrición" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Kinesiología" }));
  fireEvent.change(screen.getByPlaceholderText("Tu pregunta médica sobre este paciente"), { target: { value: "¿Aporte proteico?" } });
  fireEvent.click(screen.getByRole("button", { name: "Consultar al consejo de agentes" }));

  expect(mutate).toHaveBeenCalledWith(
    { conflictId: undefined, patientId: 5, question: "¿Aporte proteico?", areas: ["nutricionista", "kinesiologia"] },
    expect.anything(),
  );
});

it("desde un conflicto no ofrece elegir áreas", () => {
  panels([]);
  render(<AgentCouncil conflictId="9" patientId={5} canLaunch />);

  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

it("deja el razonamiento colapsado y, al abrirlo, muestra la recomendación final y la discusión", () => {
  panels([done]);
  render(<AgentCouncil conflictId="9" patientId={5} canLaunch />);

  expect(screen.getByText("Con recomendación")).toBeInTheDocument();
  expect(screen.queryByText(/Reevaluar el RASS al lado de la cama/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Razonamiento de agentes/ }));

  expect(screen.getByText(/Reevaluar el RASS al lado de la cama/)).toBeInTheDocument();
  expect(screen.getByText("Confianza media")).toBeInTheDocument();
  expect(screen.getByText("Sugerencia generada por agentes.")).toBeInTheDocument();
  expect(screen.queryByText("Mantener sedación.")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Ver la discusión \(2 intervenciones\)/ }));

  expect(screen.getByText("Mantener sedación.")).toBeInTheDocument();
  expect(screen.getByText("Ronda 2 · réplica")).toBeInTheDocument();
});

it("mientras los agentes discuten no deja lanzar otra consulta", () => {
  panels([{ ...done, status: "running", recommendation: null, turns: [] }]);
  render(<AgentCouncil conflictId="9" patientId={5} canLaunch />);

  expect(screen.getByText(/Los agentes están discutiendo/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /consultar al consejo/i })).not.toBeInTheDocument();
});

it("quien no participa del conflicto solo mira", () => {
  panels([]);
  render(<AgentCouncil conflictId="9" patientId={5} canLaunch={false} />);

  expect(screen.queryByRole("button", { name: /consultar al consejo/i })).not.toBeInTheDocument();
});
