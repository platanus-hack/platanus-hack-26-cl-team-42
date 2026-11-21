import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DEMO_EPISODE_ID } from "./fixture";
import { browserStore, createDemoEpisodeGateway, type ClosePendingInput, type EpisodeGateway } from "./gateway";
import type { SendHandoffInput } from "./model";

// Pasos 7 y 8 · Registro clínico y traspaso sobre un episodio.
// Sin backend todavía: gateway local de demo limitado al episodio ficticio.

export const episodeGateway: EpisodeGateway = createDemoEpisodeGateway({
  store: browserStore(`demo-episode-state:${DEMO_EPISODE_ID}`),
});

export const episodeKeys = {
  record: (episodeId: string) => ["episode", episodeId, "record"] as const,
  handoffs: (episodeId: string) => ["episode", episodeId, "handoffs"] as const,
  all: (episodeId: string) => ["episode", episodeId] as const,
};

export function useEpisodeRecord(episodeId: string) {
  return useQuery({
    queryKey: episodeKeys.record(episodeId),
    queryFn: () => episodeGateway.getRecord(episodeId),
  });
}

export function useHandoffs(episodeId: string) {
  return useQuery({
    queryKey: episodeKeys.handoffs(episodeId),
    queryFn: () => episodeGateway.listHandoffs(episodeId),
  });
}

export function useSendHandoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SendHandoffInput) => episodeGateway.sendHandoff(input),
    onSuccess: (handoff) =>
      queryClient.invalidateQueries({ queryKey: episodeKeys.handoffs(handoff.episodeId) }),
  });
}

export function useClosePending() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ClosePendingInput) => episodeGateway.closePending(input),
    onSuccess: (pending) => queryClient.invalidateQueries({ queryKey: episodeKeys.record(pending.episodeId) }),
  });
}

export function useResetDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (episodeId: string) => episodeGateway.reset(episodeId),
    onSuccess: (_, episodeId) => queryClient.invalidateQueries({ queryKey: episodeKeys.all(episodeId) }),
  });
}
