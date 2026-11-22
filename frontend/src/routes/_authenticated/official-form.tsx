import { createFileRoute, redirect } from "@tanstack/react-router";
import { reportIdOf } from "../../modules/episode/record";

/**
 * El registro clínico ahora vive en «Mis pacientes» (Pasar a ficha): los enlaces antiguos
 * llevan al paciente y, si apuntaban a una atención, a su informe.
 */
export const Route = createFileRoute("/_authenticated/official-form")({
  beforeLoad: ({ search }) => {
    const { episode, encounter } = search as Record<string, unknown>;
    throw redirect({
      to: "/",
      search: {
        // El router lee `episode=8` como número: se acepta en cualquiera de las dos formas.
        patient: typeof episode === "string" || typeof episode === "number" ? String(episode) : undefined,
        report: typeof encounter === "string" ? reportIdOf(encounter) : undefined,
      },
      replace: true,
    });
  },
});
