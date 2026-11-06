import React from "react";
import { Link } from "react-router";
import { ShieldAlert } from "lucide-react";
import { useCurrentUser } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
  EmptyMedia,
} from "@/components/ui/empty";

export type Role = "viewer" | "operator" | "owner";

export interface ShellRoute {
  path: string;
  title: string;
  minRole: Role;
  element: React.ReactNode;
  fullBleed?: boolean;
}

const routeModules = import.meta.glob<{ routes: ShellRoute[] }>(
  "../features/**/routes.tsx",
  { eager: true }
);

export const shellRoutes: ShellRoute[] = Object.values(routeModules).flatMap(
  (mod) => mod.routes || []
);

export function isRegistered(path: string): boolean {
  return shellRoutes.some((r) => {
    if (r.path === path) return true;
    const rParts = r.path.split("/").filter(Boolean);
    const pParts = path.split("/").filter(Boolean);
    if (rParts.length !== pParts.length) return false;
    return rParts.every((part, i) => part.startsWith(":") || part === pParts[i]);
  });
}

const ROLE_RANKS: Record<string, number> = {
  viewer: 0,
  operator: 1,
  owner: 2,
};

export function Forbidden() {
  return (
    <div className="flex h-full min-h-[400px] items-center justify-center p-6">
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ShieldAlert className="h-4 w-4" />
          </EmptyMedia>
          <EmptyTitle>Access restricted</EmptyTitle>
          <EmptyDescription className="text-sm font-normal">
            You don&apos;t have access to this page. Ask the NVR owner to change your role if you
            need it.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild>
            <Link to="/">Go to Live</Link>
          </Button>
        </EmptyContent>
      </Empty>
    </div>
  );
}

export function RequireRole({
  min,
  children,
}: {
  min: Role;
  children: React.ReactNode;
}) {
  const user = useCurrentUser();
  const userRole = user?.role || "viewer";
  const userRank = ROLE_RANKS[userRole] ?? 0;
  const minRank = ROLE_RANKS[min] ?? 0;

  if (userRank < minRank) {
    return <Forbidden />;
  }

  return <>{children}</>;
}
