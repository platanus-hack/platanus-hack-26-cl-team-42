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

export interface Person {
  name: string;
  profession: string;
}

/**
 * Reemplaza los nombres de profesionales de un texto por su rol: «Dr. Rojas (Médico UCI) registró…»
 * → «Médico UCI registró…». Si el rol se repite entre personas, queda el rol de cada una.
 */
export function anonymizeNames(text: string, people: Person[]): string {
  const known = people.filter((person) => person.name.trim() !== "");
  // Los nombres más largos primero, para no dejar a medias uno que contiene a otro.
  const byLength = [...known].sort((a, b) => b.name.length - a.name.length);
  return byLength.reduce((result, person) => {
    const name = escapeRegExp(person.name);
    const role = professionLabel(person.profession);
    return result.replace(new RegExp(`${name}(?:\\s*\\([^)]*\\))?`, "g"), role);
  }, text);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
