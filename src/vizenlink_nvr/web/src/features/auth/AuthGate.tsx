import React from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { AlertTriangle } from "lucide-react";
import { useAuthStatus } from "@/lib/queries";
import { BrandLogo } from "@/components/BrandLogo";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { safeNext } from "@/lib/safe-next";
import { AUTH_COPY } from "./copy";

export const AuthGate: React.FC = () => {
  const { data, isPending, isError, refetch } = useAuthStatus();
  const { pathname, search } = useLocation();

  // Row 1: status loading -> full-page skeleton
  if (isPending) {
    return (
      <div
        className="flex min-h-dvh flex-col items-center pt-16 px-4"
        data-testid="auth-loading-skeleton"
      >
        <BrandLogo variant="full" />
        <div className="mt-4 w-full max-w-sm">
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  // Row 2: status request fails -> NVR unreachable with Retry connection
  if (isError || !data) {
    return (
      <div
        className="flex min-h-dvh flex-col items-center pt-16 px-4"
        data-testid="auth-unreachable"
      >
        <BrandLogo variant="full" />
        <div className="mt-4 w-full max-w-sm">
          <Alert variant="destructive" role="alert">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{AUTH_COPY.NVR_UNREACHABLE_TITLE}</AlertTitle>
            <AlertDescription className="mt-2 text-sm font-normal">
              {AUTH_COPY.NVR_UNREACHABLE_BODY}
            </AlertDescription>
            <div className="mt-4">
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                {AUTH_COPY.RETRY_CONNECTION}
              </Button>
            </div>
          </Alert>
        </div>
      </div>
    );
  }

  // Row 3: initialized=false -> replace to /setup
  if (!data.initialized) {
    if (pathname !== "/setup") {
      return <Navigate to="/setup" replace />;
    }
    return <Outlet />;
  }

  // Rows 4 to 6: initialized=true, authenticated=false
  if (!data.authenticated) {
    if (pathname === "/login") {
      return <Outlet />;
    }
    if (pathname === "/setup") {
      return <Navigate to="/login" replace />;
    }
    const next = encodeURIComponent(pathname + search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  // Row 10: authenticated=true at /login or /setup -> replace to safeNext(next) or /
  if (pathname === "/login" || pathname === "/setup") {
    const nextParam = new URLSearchParams(search).get("next");
    const target = safeNext(nextParam) ?? "/";
    return <Navigate to={target} replace />;
  }

  // Authenticated at / or any protected route
  return <Outlet />;
};

export default AuthGate;
