// Live queries shared by several screens (same key = one request, shared cache).
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useRefresh } from "./live";
import type { MachineReport, Overview, RecommendationResponse } from "./types";

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/api/overview"), refetchInterval: useRefresh(6000) });
}

export function useMachine(id: string | undefined) {
  return useQuery({
    queryKey: ["machine", id],
    queryFn: () => api<MachineReport>(`/api/machines/${id}`),
    refetchInterval: useRefresh(6000),
    enabled: !!id,
  });
}

/** `preset` null = the plant's saved priorities. */
export function useRecommendation(machineId: string, preset: string | null) {
  return useQuery({
    queryKey: ["recommendation", machineId, preset],
    queryFn: () => api<RecommendationResponse>(`/api/machines/${machineId}/recommendation`, { body: preset ? { preset } : {} }),
    staleTime: 60_000,
  });
}
