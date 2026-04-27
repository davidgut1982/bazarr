import { useMutation, useQuery } from "@tanstack/react-query";
import { QueryKeys } from "@/apis/queries/keys";
import api from "@/apis/raw";

export const useJellyfinLibrariesQuery = (
  enabled: boolean = true,
  url?: string,
  apikey?: string,
  verifySsl?: boolean,
) => {
  return useQuery({
    queryKey: [QueryKeys.Jellyfin, "libraries", url, apikey, verifySsl],
    queryFn: () => api.jellyfin.libraries(url, apikey, verifySsl),
    enabled,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};

export const useJellyfinTestConnectionMutation = () => {
  return useMutation({
    mutationFn: (params: {
      url: string;
      apikey: string;
      verifySsl?: boolean;
    }) =>
      api.jellyfin.testConnection(params.url, params.apikey, params.verifySsl),
  });
};

export const useJellyfinRefreshLibrariesMutation = () => {
  return useMutation({
    mutationFn: () => api.jellyfin.refreshLibraries(),
  });
};
