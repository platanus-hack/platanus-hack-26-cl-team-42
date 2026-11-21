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
}

export const WORKFLOW_STEPS = [
  {
    id: "recordings",
    label: "Grabar audio",
    summary: "Captura el dictado o la consulta de cada profesional.",
    path: "/recordings",
  },
  {
    id: "transcription",
    label: "Transcribir",
    summary: "Convierte los audios grabados en texto.",
    path: "/transcription",
  },
  {
    id: "templates",
    label: "Parseo a plantillas",
    summary: "Estructura el texto según la plantilla del informe.",
    path: "/templates",
  },
  {
    id: "concepts",
    label: "Homologar conceptos",
    summary: "Unifica términos distintos que significan lo mismo.",
    path: "/concepts",
  },
  {
    id: "consolidation",
    label: "Consolidar informes",
    summary: "Reúne los informes de todos los profesionales en uno.",
    path: "/consolidation",
  },
  {
    id: "actionables",
    label: "Activar accionables",
    summary: "Convierte hallazgos en tareas o recomendaciones concretas.",
    path: "/actionables",
  },
  {
    id: "official-form",
    label: "Registro clínico",
    summary: "Registro prellenado por atención, listo para copiar a la ficha institucional.",
    path: "/official-form",
  },
  {
    id: "handoff",
    label: "Traspaso",
    summary: "Entrega en conjunto los pacientes que atendiste a otra persona del equipo.",
    path: "/handoff",
  },
] as const satisfies readonly WorkflowStep[];

export type WorkflowStepId = (typeof WORKFLOW_STEPS)[number]["id"];

export function getWorkflowStep(id: WorkflowStepId) {
  const index = WORKFLOW_STEPS.findIndex((step) => step.id === id);
  return {
    index,
    step: WORKFLOW_STEPS[index],
    previous: WORKFLOW_STEPS[index - 1] as (typeof WORKFLOW_STEPS)[number] | undefined,
    next: WORKFLOW_STEPS[index + 1] as (typeof WORKFLOW_STEPS)[number] | undefined,
  };
}
