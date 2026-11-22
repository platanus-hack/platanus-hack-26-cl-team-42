import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { patientKeys } from "../patients/api";
import { episodeGateway, type ChartInput, type ClosePendingInput } from "./gateway";
import type { SendHandoffInput } from "./model";

const recordKeys = ["episode-records"] as const;
const handoffKeys = ["professional-handoffs"] as const;
const teamKeys = ["episode-team"] as const;

/** Los registros clínicos de los pacientes asignados al usuario activo. */
export function useEpisodeRecords() {
  return useQuery({ queryKey: recordKeys, queryFn: () => episodeGateway.listRecords() });
}

/** Quién eres y a quiénes puedes traspasar. */
export function useTeam() {
  return useQuery({ queryKey: teamKeys, queryFn: () => episodeGateway.getTeam() });
}

export function useHandoffs() {
  return useQuery({ queryKey: handoffKeys, queryFn: () => episodeGateway.listHandoffs() });
}

export function useSendHandoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SendHandoffInput) => episodeGateway.sendHandoff(input),
    // Quien recibe pasa a tener a los pacientes: se refrescan sus listas.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: handoffKeys }),
        queryClient.invalidateQueries({ queryKey: patientKeys }),
        queryClient.invalidateQueries({ queryKey: recordKeys }),
      ]),
  });
}

export function useClosePending() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ClosePendingInput) => episodeGateway.closePending(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recordKeys }),
  });
}

/** Confirma (o deshace) que tus atenciones se pasaron a la ficha: cambia el registro y la bandeja. */
export function useChartMark(action: "mark" | "unmark") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChartInput) =>
      action === "mark" ? episodeGateway.markCharted(input) : episodeGateway.unmarkCharted(input),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: recordKeys }),
        queryClient.invalidateQueries({ queryKey: patientKeys }),
      ]),
  });
}
