import { createFileRoute, redirect } from "@tanstack/react-router";

/** Los informes ahora viven en «Mis pacientes»: los enlaces antiguos siguen funcionando. */
export const Route = createFileRoute("/_authenticated/reports")({
  beforeLoad: ({ search }) => {
    const { patient, report, section } = search as Record<string, unknown>;
    throw redirect({
      to: "/",
      search: {
        patient: patient === "all" || patient === undefined ? undefined : String(patient),
        report: report === undefined ? undefined : String(report),
        section: typeof section === "string" ? section : undefined,
      },
      replace: true,
    });
  },
});
