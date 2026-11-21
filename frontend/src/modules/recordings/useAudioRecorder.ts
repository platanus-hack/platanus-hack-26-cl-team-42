import { useCallback, useEffect, useRef, useState } from "react";
import { pickMimeType, rmsLevel } from "./recorderFormat";

/**
 * Grabación nativa en el navegador (MediaRecorder).
 *
 * El audio nunca sale del dispositivo hasta que el profesional decide
 * guardarlo: se acumula en memoria y se entrega como `Blob` al detener.
 */

export type RecorderStatus = "idle" | "requesting" | "recording" | "paused" | "stopped" | "error";

export interface RecordedAudio {
  blob: Blob;
  url: string;
  mimeType: string;
  durationSeconds: number;
  startedAt: Date;
}

/** Número de barras de la forma de onda en vivo. */
export const LEVEL_BARS = 32;

export function useAudioRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array(LEVEL_BARS).fill(0));
  const [audio, setAudio] = useState<RecordedAudio | null>(null);

  const session = useRef<RecordingSession | null>(null);

  const start = useCallback(async () => {
    if (!isRecordingSupported()) {
      setStatus("error");
      setError("Este navegador no permite grabar audio. Usa la opción «Subir archivo».");
      return;
    }
    setError(null);
    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      session.current = new RecordingSession(stream, {
        onTick: setElapsedSeconds,
        onLevel: (level) => setLevels((previous) => [...previous.slice(1), level]),
        onStop: (recorded) => {
          setAudio(recorded);
          setStatus("stopped");
        },
      });
      setElapsedSeconds(0);
      setLevels(Array(LEVEL_BARS).fill(0));
      setStatus("recording");
    } catch (cause) {
      setStatus("error");
      setError(describeMediaError(cause));
    }
  }, []);

  const pause = useCallback(() => {
    session.current?.pause();
    setStatus("paused");
  }, []);

  const resume = useCallback(() => {
    session.current?.resume();
    setStatus("recording");
  }, []);

  const stop = useCallback(() => {
    session.current?.stop();
    session.current = null;
  }, []);

  /** Descarta la toma actual (grabando o detenida) y vuelve al inicio. */
  const reset = useCallback(() => {
    session.current?.discard();
    session.current = null;
    setAudio((previous) => {
      if (previous) URL.revokeObjectURL(previous.url);
      return null;
    });
    setElapsedSeconds(0);
    setLevels(Array(LEVEL_BARS).fill(0));
    setError(null);
    setStatus("idle");
  }, []);

  // Al desmontar: liberar micrófono y memoria.
  useEffect(
    () => () => {
      session.current?.discard();
    },
    [],
  );
  useEffect(() => () => {
    if (audio) URL.revokeObjectURL(audio.url);
  }, [audio]);

  // Evitar perder un dictado al cerrar o recargar la pestaña.
  const hasUnsavedAudio = status === "recording" || status === "paused" || status === "stopped";
  useEffect(() => {
    if (!hasUnsavedAudio) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedAudio]);

  return { status, error, elapsedSeconds, levels, audio, start, pause, resume, stop, reset };
}

export function isRecordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

interface SessionCallbacks {
  onTick: (seconds: number) => void;
  onLevel: (level: number) => void;
  onStop: (audio: RecordedAudio) => void;
}

/**
 * Una toma: micrófono + MediaRecorder + analizador de nivel + cronómetro que
 * descuenta las pausas. Vive fuera de React para no depender de renders.
 */
class RecordingSession {
  private readonly recorder: MediaRecorder;
  private readonly chunks: Blob[] = [];
  private readonly startedAt = new Date();
  private readonly audioContext: AudioContext | null;
  private readonly analyser: AnalyserNode | null;
  private readonly samples: Uint8Array<ArrayBuffer>;
  private accumulatedMs = 0;
  private resumedAt: number | null = null;
  private timer: number;
  private frame = 0;
  private discarded = false;
  private released = false;
  private wakeLock: WakeLockSentinel | null = null;
  private readonly stream: MediaStream;
  private readonly callbacks: SessionCallbacks;

  constructor(stream: MediaStream, callbacks: SessionCallbacks) {
    this.stream = stream;
    this.callbacks = callbacks;
    const mimeType = pickMimeType((type) => MediaRecorder.isTypeSupported(type));
    this.recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 64_000 });
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.recorder.onstop = () => this.finish();
    // Fragmentos de 1 s: si algo falla a mitad, lo grabado sigue en memoria.
    this.recorder.start(1000);
    this.resumedAt = performance.now();

    this.audioContext = typeof AudioContext !== "undefined" ? new AudioContext() : null;
    this.analyser = this.audioContext?.createAnalyser() ?? null;
    this.samples = new Uint8Array(this.analyser?.fftSize ?? 0);
    if (this.audioContext && this.analyser) {
      this.audioContext.createMediaStreamSource(stream).connect(this.analyser);
      this.sampleLevel();
    }

    this.timer = window.setInterval(() => this.callbacks.onTick(this.elapsedMs() / 1000), 250);
    void this.keepScreenAwake();
  }

  pause() {
    if (this.recorder.state !== "recording") return;
    this.recorder.pause();
    this.freezeElapsedTime();
  }

  resume() {
    if (this.recorder.state !== "paused") return;
    this.recorder.resume();
    this.resumedAt = performance.now();
  }

  stop() {
    if (this.recorder.state === "inactive") return;
    this.freezeElapsedTime();
    this.recorder.stop();
  }

  discard() {
    this.discarded = true;
    this.stop();
    this.release();
  }

  private freezeElapsedTime() {
    this.accumulatedMs = this.elapsedMs();
    this.resumedAt = null;
  }

  private elapsedMs() {
    const running = this.resumedAt === null ? 0 : performance.now() - this.resumedAt;
    return this.accumulatedMs + running;
  }

  private sampleLevel = () => {
    if (!this.analyser || this.released) return;
    this.analyser.getByteTimeDomainData(this.samples);
    this.callbacks.onLevel(this.recorder.state === "recording" ? rmsLevel(this.samples) : 0);
    // ~15 fps es suficiente para la forma de onda y barato en móviles.
    this.frame = window.setTimeout(() => requestAnimationFrame(this.sampleLevel), 66);
  };

  private finish() {
    const durationSeconds = this.elapsedMs() / 1000;
    this.release();
    if (this.discarded) return;
    const mimeType = this.recorder.mimeType || this.chunks[0]?.type || "audio/webm";
    const blob = new Blob(this.chunks, { type: mimeType });
    this.callbacks.onStop({
      blob,
      url: URL.createObjectURL(blob),
      mimeType,
      durationSeconds,
      startedAt: this.startedAt,
    });
  }

  private release() {
    if (this.released) return;
    this.released = true;
    window.clearInterval(this.timer);
    window.clearTimeout(this.frame);
    this.stream.getTracks().forEach((track) => track.stop());
    void this.audioContext?.close().catch(() => undefined);
    void this.wakeLock?.release().catch(() => undefined);
    this.wakeLock = null;
  }

  /** En móviles, evita que la pantalla se apague y corte la grabación. */
  private async keepScreenAwake() {
    try {
      this.wakeLock = (await navigator.wakeLock?.request("screen")) ?? null;
    } catch {
      // No soportado o denegado: la grabación sigue igual.
    }
  }
}

function describeMediaError(cause: unknown): string {
  const name = cause instanceof DOMException ? cause.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Se negó el acceso al micrófono. Habilítalo en los permisos del navegador.";
  }
  if (name === "NotFoundError") return "No se encontró un micrófono en este dispositivo.";
  if (name === "NotReadableError") return "El micrófono está siendo usado por otra aplicación.";
  return "No se pudo iniciar la grabación.";
}
