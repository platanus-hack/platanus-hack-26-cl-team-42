import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DEMO_EPISODE_ID } from "./fixture";
import { browserStore, createDemoEpisodeGateway, type ClosePendingInput, type EpisodeGateway } from "./gateway";
import type { SendHandoffInput } from "./model";

const episodeGateway: EpisodeGateway = createDemoEpisodeGateway({
  store: browserStore(`demo-episode-state:${DEMO_EPISODE_ID}`),
});

const recordKeys = ["episode-records"] as const;
const handoffKeys = ["professional-handoffs"] as const;

export function useEpisodeRecords() {
  return useQuery({ queryKey: recordKeys, queryFn: () => episodeGateway.listRecords() });
}

export function useHandoffs(professionalId: string) {
  return useQuery({
    queryKey: [...handoffKeys, professionalId],
    queryFn: () => episodeGateway.listHandoffs(professionalId),
  });
}

export function useSendHandoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SendHandoffInput) => episodeGateway.sendHandoff(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: handoffKeys }),
  });
}

export function useClosePending() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ClosePendingInput) => episodeGateway.closePending(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: recordKeys }),
  });
}

export function useResetDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => episodeGateway.reset(),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: recordKeys }),
      queryClient.invalidateQueries({ queryKey: handoffKeys }),
    ]),
  });
}
