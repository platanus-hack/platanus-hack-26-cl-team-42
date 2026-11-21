import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 6 · Activación de accionables a partir del informe consolidado.

export type ActionableStatus = "suggested" | "active" | "done";

export interface Actionable {
  id: string;
  title: string;
  description: string;
  status: ActionableStatus;
  /** Sección del informe consolidado que originó el accionable. */
  sourceSection: string;
}

export interface ActionablesGateway {
  list(): Promise<Actionable[]>;
  activate(id: string): Promise<Actionable>;
}

export const actionablesGateway: ActionablesGateway = {
  list: async () => [],
  activate: notConnected("actionables.activate"),
};

export const actionableKeys = ["actionables"] as const;

export function useActionables() {
  return useQuery({
    queryKey: actionableKeys,
    queryFn: () => actionablesGateway.list(),
  });
}

export function useActivateActionable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => actionablesGateway.activate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: actionableKeys }),
  });
}
