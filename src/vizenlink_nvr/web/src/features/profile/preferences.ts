import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { type AuthStatus, useCurrentUser } from "@/lib/queries";
import { useUiStore, type Theme, type ViewMode } from "@/stores/ui";

type Change = { theme: Theme } | { view_mode: ViewMode };

export function useAccountPreferences() {
  const user = useCurrentUser();
  const client = useQueryClient();
  const save = useMutation({
    scope: { id: "account-preferences" },
    mutationFn: async (change: Change) => {
      const current = client.getQueryData<AuthStatus>(["authStatus"])?.user;
      if (!user || current?.id !== user.id) throw new Error("Sign in again to save preferences.");
      await apiFetch("/api/v1/auth/preferences", { method: "PATCH", body: change });
      if (client.getQueryData<AuthStatus>(["authStatus"])?.user?.id !== user.id) return;
      client.setQueryData<AuthStatus>(["authStatus"], previous => previous?.user
        ? { ...previous, user: { ...previous.user, ...change } } : previous);
      useUiStore.setState("theme" in change ? { theme: change.theme } : { viewMode: change.view_mode });
    },
    onError: error => toast.error(error.message),
  });
  return {
    setTheme: (theme: Theme) => save.mutate({ theme }),
    setViewMode: (view_mode: ViewMode) => save.mutate({ view_mode }),
  };
}
