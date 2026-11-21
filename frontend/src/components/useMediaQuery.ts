import { useEffect, useState } from "react";

/** Si la pantalla cumple una media query (p. ej. «(min-width: 900px)»); se actualiza al girar el equipo. */
export function useMediaQuery(query: string): boolean {
  const supported = typeof window !== "undefined" && typeof window.matchMedia === "function";
  const [matches, setMatches] = useState(() => (supported ? window.matchMedia(query).matches : false));

  useEffect(() => {
    if (!supported) return;
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query, supported]);

  return matches;
}
