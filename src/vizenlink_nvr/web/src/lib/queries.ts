import { QueryClient, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  permissions: string[];
}

export interface AuthStatus {
  initialized: boolean;
  authenticated: boolean;
  user?: AuthUser | null;
  site_timezone: string | null;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: true,
      },
    },
  });
}

export const queryClient = createQueryClient();

export function useAuthStatus() {
  return useQuery<AuthStatus>({
    queryKey: ["authStatus"],
    queryFn: () => apiFetch<AuthStatus>("/api/v1/auth/status"),
    staleTime: 0,
  });
}

export function useCurrentUser(): AuthUser | null {
  const { data } = useAuthStatus();
  return data?.user ?? null;
}
