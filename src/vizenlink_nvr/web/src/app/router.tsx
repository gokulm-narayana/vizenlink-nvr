import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
} from "react-router";
import { AuthGate } from "@/features/auth/AuthGate";
import { LoginPage } from "@/features/auth/LoginPage";
import { SetupPage } from "@/features/auth/SetupPage";
import { AppShell } from "@/components/shell/AppShell";
import { shellRoutes, RequireRole } from "@/app/routes";
import { queryClient } from "@/lib/queries";
import { setUnauthorizedHandler } from "@/lib/api";

export function createAppRoutes(): RouteObject[] {
  return [
    {
      element: <AuthGate />,
      children: [
        {
          path: "/login",
          element: <LoginPage />,
        },
        {
          path: "/setup",
          element: <SetupPage />,
        },
        {
          element: <AppShell />,
          children: [
            ...shellRoutes.map((r): RouteObject => {
              if (r.path === "/") {
                return {
                  index: true,
                  element: <RequireRole min={r.minRole}>{r.element}</RequireRole>,
                  handle: { title: r.title, fullBleed: r.fullBleed },
                };
              }
              return {
                path: r.path.startsWith("/") ? r.path.slice(1) : r.path,
                element: <RequireRole min={r.minRole}>{r.element}</RequireRole>,
                handle: { title: r.title, fullBleed: r.fullBleed },
              };
            }),
            {
              path: "*",
              element: <Navigate to="/" replace />,
            },
          ],
        },
      ],
    },
  ];
}

export const router = createBrowserRouter(createAppRoutes());

setUnauthorizedHandler(() => {
  queryClient.clear();
  const loc = router.state.location;
  const next = encodeURIComponent(loc.pathname + loc.search);
  void router.navigate(`/login?next=${next}`, {
    replace: true,
    state: { sessionEnded: true },
  });
});
