/**
 * Active UI language.
 *
 * The backend resolves translatable strings (gettext / `_()`) via committed
 * django.po catalogs with a live DB overlay (see `backend/lib/dbi18n`).
 * Language is negotiated from the `Accept-Language` header. This module holds
 * the chosen language, persists it,
 * and exposes `withLanguage()` to stamp the header onto API requests. Because
 * the API layer uses plain `fetch` (outside React), the state lives in a small
 * external store that components subscribe to via `useLanguage()`.
 */

import { useSyncExternalStore } from "react";

export type Language = "en" | "es";

export const LANGUAGES: { code: Language; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
];

const STORAGE_KEY = "app.language";
const listeners = new Set<() => void>();

function readInitial(): Language {
  if (typeof localStorage === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "es" || stored === "en" ? stored : "en";
}

let current: Language = readInitial();

export function getLanguage(): Language {
  return current;
}

export function setLanguage(language: Language): void {
  if (language === current) return;
  current = language;
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Ignore storage failures (e.g. private mode); state still lives in memory.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Merge the active language into a fetch init as an `Accept-Language` header. */
export function withLanguage(init: RequestInit = {}): RequestInit {
  return {
    ...init,
    headers: { ...(init.headers ?? {}), "Accept-Language": current },
  };
}

/** Subscribe a React component to the active language. */
export function useLanguage(): {
  language: Language;
  setLanguage: (language: Language) => void;
} {
  const language = useSyncExternalStore(subscribe, getLanguage, getLanguage);
  return { language, setLanguage };
}
