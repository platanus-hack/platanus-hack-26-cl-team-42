/**
 * Flujo de trabajo de la aplicación.
 *
 * Fuente única de verdad para el orden de los pasos: alimenta la navegación
 * lateral, la vista general del inicio y el pie de cada módulo (anterior /
 * siguiente). Agregar o reordenar un paso se hace solo aquí.
 */

export interface WorkflowStep {
  id: string;
  label: string;
  summary: string;
  path: string;
  /** Fuera de la navegación por ahora: la ruta sigue existiendo, pero no se ofrece en el flujo. */
  hidden: boolean;
  /** El paso ya habla con su backend. */
  connected: boolean;
}

export const WORKFLOW_STEPS = [
  {
    id: "patients",
    label: "Mis pacientes",
    summary: "Tus pacientes asignados: graba sus dictados, valida sus informes y revisa su estado.",
    path: "/",
    hidden: false,
    connected: true,
  },
  {
    id: "recordings",
    label: "Grabar audio",
    summary: "Graba o sube el dictado y sigue su proceso: transcripción, parseo, homologación e informe.",
    path: "/recordings",
    hidden: true,
    connected: true,
  },
  {
    id: "reports",
    label: "Informes",
    summary: "Informes de tus pacientes: resumen, detalle por profesional y consultas con IA.",
    path: "/reports",
    hidden: true,
    connected: true,
  },
  {
    id: "official-form",
    label: "Registro clínico",
    summary: "Registro prellenado por atención, listo para copiar a la ficha institucional.",
    path: "/official-form",
    hidden: false,
    connected: true,
  },
  {
    id: "reconciliation",
    label: "Conflictos",
    summary: "Concilia las diferencias entre lo reportado por distintos profesionales antes de actualizar la versión oficial.",
    path: "/reconciliation",
    hidden: false,
    connected: true,
  },
  {
    id: "handoff",
    label: "Traspaso",
    summary: "Entrega en conjunto los pacientes que atendiste a otra persona del equipo.",
    path: "/handoff",
    hidden: false,
    connected: true,
  },
  {
    id: "transcription",
    label: "Transcribir",
    summary: "Convierte los audios grabados en texto.",
    path: "/transcription",
    hidden: true,
    connected: false,
  },
  {
    id: "templates",
    label: "Parseo a plantillas",
    summary: "Estructura el texto según la plantilla del informe.",
    path: "/templates",
    hidden: true,
    connected: false,
  },
  {
    id: "concepts",
    label: "Homologar conceptos",
    summary: "Unifica términos distintos que significan lo mismo.",
    path: "/concepts",
    hidden: true,
    connected: false,
  },
  {
    id: "consolidation",
    label: "Consolidar informes",
    summary: "Reúne los informes de todos los profesionales en uno.",
    path: "/consolidation",
    hidden: true,
    connected: false,
  },
  {
    id: "actionables",
    label: "Activar accionables",
    summary: "Convierte hallazgos en tareas o recomendaciones concretas.",
    path: "/actionables",
    hidden: true,
    connected: false,
  },
] as const satisfies readonly WorkflowStep[];

export type WorkflowStepId = (typeof WORKFLOW_STEPS)[number]["id"];

/** Los pasos que se ofrecen en la navegación, en orden. */
export const VISIBLE_STEPS = WORKFLOW_STEPS.filter((step) => !step.hidden);

export function getWorkflowStep(id: WorkflowStepId) {
  // Un paso oculto se ubica dentro del flujo completo; uno visible, dentro de los visibles.
  const steps: readonly WorkflowStep[] = VISIBLE_STEPS.some((step) => step.id === id) ? VISIBLE_STEPS : WORKFLOW_STEPS;
  const index = steps.findIndex((step) => step.id === id);
  return {
    steps,
    index,
    step: steps[index],
    previous: steps[index - 1] as WorkflowStep | undefined,
    next: steps[index + 1] as WorkflowStep | undefined,
  };
}
