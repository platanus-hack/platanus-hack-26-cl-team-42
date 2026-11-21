import { professionLabel } from "../recordings/professions";

const ORDINALS = ["Primer", "Segundo", "Tercer", "Cuarto", "Quinto", "Sexto", "Séptimo", "Octavo", "Noveno", "Décimo"];

/** `1` → «Primer informe», `3` → «Tercer informe», `12` → «Informe n.º 12». */
export function reportOrdinal(sequence: number): string {
  const ordinal = ORDINALS[sequence - 1];
  return ordinal ? `${ordinal} informe` : `Informe n.º ${sequence}`;
}

/** «Primer informe de Kinesiología» */
export function reportTitle(sequence: number, profession: string): string {
  return `${reportOrdinal(sequence)} de ${professionLabel(profession)}`;
}

export function sectionAnchor(key: string): string {
  return `report-section-${key}`;
}
