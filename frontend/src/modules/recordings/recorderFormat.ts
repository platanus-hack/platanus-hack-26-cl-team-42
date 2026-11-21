/**
 * Utilidades puras del grabador: formato de audio y presentación.
 * Separadas del hook para poder probarlas sin APIs del navegador.
 */

/** Formatos en orden de preferencia. Opus en WebM (Chrome/Firefox), AAC en MP4 (Safari). */
export const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
] as const;

/** Primer formato soportado; `undefined` deja que el navegador elija. */
export function pickMimeType(isTypeSupported: (type: string) => boolean): string | undefined {
  return PREFERRED_MIME_TYPES.find((type) => isTypeSupported(type));
}

/** Extensión de archivo para un MIME (`audio/webm;codecs=opus` → `webm`). */
export function extensionFor(mimeType: string): string {
  const base = mimeType.split(";")[0].trim().toLowerCase();
  const known: Record<string, string> = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
  };
  return known[base] ?? "bin";
}

/** `75.4` → `01:15`; pasada la hora, `1:01:15`. */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) return "--:--";
  const seconds = Math.floor(totalSeconds);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** `1536000` → `1,5 MB`. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("es-CL", { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/** Nivel RMS (0–1) de una muestra de forma de onda en bytes (128 = silencio). */
export function rmsLevel(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) {
    const centered = (sample - 128) / 128;
    sum += centered * centered;
  }
  // La voz rara vez pasa de ~0.3 RMS: amplificar para que las barras se muevan.
  return Math.min(1, Math.sqrt(sum / samples.length) * 3);
}
