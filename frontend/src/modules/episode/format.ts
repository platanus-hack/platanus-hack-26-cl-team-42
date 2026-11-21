/** Las horas clínicas de la demo se muestran siempre en hora de Chile. */
const CLINICAL_TIME = new Intl.DateTimeFormat("es-CL", {
  timeZone: "America/Santiago",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatClinicalTime(iso: string): string {
  return CLINICAL_TIME.format(new Date(iso));
}
