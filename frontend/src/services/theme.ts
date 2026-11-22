/**
 * Apariencia de la interfaz (claro / oscuro).
 *
 * Parte de la preferencia guardada o, si no hay, de la del sistema operativo. Se guarda en
 * `localStorage` y se expone a React con `useAppearance()`, igual que el idioma
 * (ver `language.ts`).
 */

import { useSyncExternalStore } from "react";

export type Appearance = "light" | "dark";

const STORAGE_KEY = "app.appearance";
const listeners = new Set<() => void>();

let current: Appearance = readInitial();

/** Suscribe un componente a la apariencia activa. */
export function useAppearance(): {
  appearance: Appearance;
  toggleAppearance: () => void;
} {
  const appearance = useSyncExternalStore(subscribe, getAppearance, getAppearance);
  return { appearance, toggleAppearance };
}

export function getAppearance(): Appearance {
  return current;
}

export function setAppearance(appearance: Appearance): void {
  if (appearance === current) return;
  current = appearance;
  try {
    localStorage.setItem(STORAGE_KEY, appearance);
  } catch {
    // Sin almacenamiento (p. ej. modo privado) el estado vive solo en memoria.
  }
  listeners.forEach((listener) => listener());
}

function toggleAppearance(): void {
  setAppearance(current === "dark" ? "light" : "dark");
}

function readInitial(): Appearance {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Sin almacenamiento: se usa la preferencia del sistema.
  }
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
