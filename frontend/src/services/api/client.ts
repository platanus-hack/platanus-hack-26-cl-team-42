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
  const response = await fetch(
    `${API_PREFIX}${path}`,
    withLanguage({
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    }),
  );
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

/** Operación de un adaptador sin backend: falla de forma explícita y visible. */
export function notConnected(endpoint: string): () => Promise<never> {
  return async () => {
    throw new NotConnectedError(endpoint);
  };
}
