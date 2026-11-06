import {
  createBrowserRouter,
  type RouteObject,
} from "react-router";
import { AuthGate } from "@/features/auth/AuthGate";
import { LoginPage } from "@/features/auth/LoginPage";
import { SetupPage } from "@/features/auth/SetupPage";
import LegacyApp from "@/legacy/LegacyApp";
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
          path: "*",
          element: <LegacyApp />,
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
