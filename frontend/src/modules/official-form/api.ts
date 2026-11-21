import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notConnected } from "../../services/api/client";

// Módulo 7 · Rellenado de la ficha oficial con la información consolidada.

export interface OfficialFormField {
  key: string;
  label: string;
  value: string;
  required: boolean;
}

export interface OfficialForm {
  id: string;
  title: string;
  /** Informe consolidado del que se alimentan los campos. */
  consolidatedReportId: string;
  fields: OfficialFormField[];
}

export interface OfficialFormGateway {
  getCurrent(): Promise<OfficialForm | null>;
  save(id: string, values: Record<string, string>): Promise<OfficialForm>;
}

export const officialFormGateway: OfficialFormGateway = {
  getCurrent: async () => null,
  save: notConnected("official-form.save"),
};

export const officialFormKeys = ["official-form"] as const;

export function useOfficialForm() {
  return useQuery({
    queryKey: officialFormKeys,
    queryFn: () => officialFormGateway.getCurrent(),
  });
}

export function useSaveOfficialForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, values }: { id: string; values: Record<string, string> }) =>
      officialFormGateway.save(id, values),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: officialFormKeys }),
  });
}
