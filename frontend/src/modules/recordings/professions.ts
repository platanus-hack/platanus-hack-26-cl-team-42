// Tipos de profesional que dictan; los valores coinciden con
// `ClinicalTemplate.Profession` en el backend y deciden la plantilla clínica.

export const PROFESSIONS = [
  { value: "medico", label: "Médico UCI" },
  { value: "especialista", label: "Especialista (interconsulta)" },
  { value: "enfermeria", label: "Enfermería" },
  { value: "tens", label: "TENS" },
  { value: "kinesiologia", label: "Kinesiología" },
] as const;

export type Profession = (typeof PROFESSIONS)[number]["value"];

export function professionLabel(value: string): string {
  return PROFESSIONS.find((profession) => profession.value === value)?.label ?? value;
}
