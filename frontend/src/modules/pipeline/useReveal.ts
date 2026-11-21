import { useEffect, useState } from "react";

/**
 * Cuenta de 0 a `target` de a uno cada `intervalMs`, para mostrar de a poco lo que el
 * backend ya tiene listo (con la caché todo llega de golpe y no se vería el proceso).
 */
export function useReveal(target: number, intervalMs: number, enabled: boolean): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled || count >= target) return;
    const timer = setTimeout(() => setCount((current) => current + 1), intervalMs);
    return () => clearTimeout(timer);
  }, [enabled, count, target, intervalMs]);

  return enabled ? Math.min(count, target) : 0;
}
