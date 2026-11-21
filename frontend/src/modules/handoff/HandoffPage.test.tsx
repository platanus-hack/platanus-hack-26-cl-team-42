import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HandoffPage } from "./HandoffPage";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ to, search, children }: { to: string; search?: Record<string, string>; children: ReactNode }) => (
    <a href={search ? `${to}?${new URLSearchParams(search)}` : to}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  });
});

afterEach(() => {
  cleanup();
  window.localStorage?.clear();
  navigate.mockClear();
  vi.unstubAllGlobals();
});

it("envía los dos pacientes atendidos en una sola entrega y abre el origen correcto", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <Theme><HandoffPage search={{}} /></Theme>
    </QueryClientProvider>,
  );

  const preview = await screen.findByRole("group", { name: "Pacientes del traspaso" });
  expect(within(preview).getAllByRole("button")).toHaveLength(2);
  expect(within(preview).queryByRole("button", { name: /DEMO-003/ })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Enviar traspaso" }));
  const confirmation = screen.getByRole("alertdialog");
  expect(confirmation).toHaveTextContent("una sola entrega con 2 pacientes");
  fireEvent.click(within(confirmation).getByRole("button", { name: "Confirmar envío" }));
  fireEvent.click(await screen.findByRole("button", { name: "Abrir vista receptora" }));
  expect(navigate).toHaveBeenCalledOnce();
  const { search } = navigate.mock.calls[0][0];
  expect(search).toMatchObject({ as: "prof-kine", tab: "received" });

  view.rerender(
    <QueryClientProvider client={queryClient}>
      <Theme><HandoffPage search={search} /></Theme>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("heading", { name: "Traspaso de 2 pacientes" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Recibidos \(1\)/, selected: true })).toBeInTheDocument();

  const patients = screen.getByRole("group", { name: "Pacientes del traspaso" });
  fireEvent.click(within(patients).getByRole("button", { name: /DEMO-002/ }));
  const sourceLinks = screen.getAllByRole("link", { name: "ver atención de origen" });
  expect(sourceLinks[0]).toHaveAttribute("href", "/official-form?episode=demo-episode-002&encounter=enc-demo-002-nurse");

  fireEvent.click(screen.getByRole("button", { name: "Cerrar pendiente: Coordinar la próxima movilización" }));
  expect(await screen.findByText("Ahora: cerrado")).toBeInTheDocument();
  expect(screen.getByText("Abierto")).toBeInTheDocument();
});
