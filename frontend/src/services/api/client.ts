/**
 * Cliente HTTP común para los módulos del backend.
 *
 * Cada módulo habla con su propio prefijo bajo `/-/api/<módulo>/` a través de
 * `apiRequest`. Mientras el backend de un módulo no exista, su adaptador
 * (`gateway`) es el de "sin conexión": ver `notConnected`.
 */

import { withLanguage } from "../language";

const API_PREFIX = "/-/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class NotConnectedError extends Error {
  readonly endpoint: string;

  constructor(endpoint: string) {
    super(`Sin conexión: "${endpoint}" todavía no está implementado.`);
    this.name = "NotConnectedError";
    this.endpoint = endpoint;
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Con FormData el navegador fija el Content-Type (multipart + boundary).
  const isForm = init.body instanceof FormData;
  const response = await fetch(
    apiUrl(path),
    withLanguage({
      ...init,
      credentials: "include",
      headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(init.headers ?? {}) },
    }),
  );
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** URL absoluta (mismo origen) de un recurso de la API, p. ej. para `<audio src>`. */
export function apiUrl(path: string): string {
  return `${API_PREFIX}${path}`;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Cuerpo vacío o no JSON: usar el estado HTTP.
  }
  return `${response.status} ${response.statusText}`;
}

/** Operación de un adaptador sin backend: falla de forma explícita y visible. */
export function notConnected(endpoint: string): () => Promise<never> {
  return async () => {
    throw new NotConnectedError(endpoint);
  };
}
