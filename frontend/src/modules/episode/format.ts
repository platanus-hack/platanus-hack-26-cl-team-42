/** Las horas clínicas se muestran siempre en hora de Chile. */
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

/** Tiempo transcurrido entre dos instantes, p. ej. «2 h 50 min» o «45 min». */
export function formatElapsed(fromIso: string, toIso: string): string {
  const minutes = Math.max(0, Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 60_000));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}
