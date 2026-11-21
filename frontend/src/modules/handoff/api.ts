import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 8 · Traspaso del caso a otras personas del equipo.

export interface Person {
  id: string;
  name: string;
  role: string;
}

export type HandoffStatus = "sent" | "accepted" | "returned";

export interface Handoff {
  id: string;
  recipient: Person;
  note: string;
  status: HandoffStatus;
  createdAt: string;
}

export interface CreateHandoffInput {
  recipientId: string;
  note: string;
  /** Ficha u informe que se traspasa. */
  consolidatedReportId: string;
}

export interface HandoffGateway {
  list(): Promise<Handoff[]>;
  searchPeople(query: string): Promise<Person[]>;
  create(input: CreateHandoffInput): Promise<Handoff>;
}

export const handoffGateway: HandoffGateway = {
  list: async () => [],
  searchPeople: async () => [],
  create: notConnected("handoff.create"),
};

export const handoffKeys = ["handoffs"] as const;

export function useHandoffs() {
  return useQuery({
    queryKey: handoffKeys,
    queryFn: () => handoffGateway.list(),
  });
}

export function useCreateHandoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateHandoffInput) => handoffGateway.create(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: handoffKeys }),
  });
}
