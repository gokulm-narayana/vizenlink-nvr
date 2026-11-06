import React from "react";
import { Link, Outlet, useMatches } from "react-router";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppSidebar } from "./AppSidebar";
import { UserMenu } from "./UserMenu";
import { ViewModeToggle } from "./ViewModeToggle";
import { ThemeSync } from "./ThemeSync";
import { BrandLogo } from "@/components/BrandLogo";
import { AlertsBanner } from "@/legacy/AlertsBanner";
import { useAlerts } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";

interface RouteHandle {
  title?: string;
  fullBleed?: boolean;
}

export const AppShell: React.FC = () => {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const dismissAlert = useUiStore((s) => s.dismissAlert);
  const { data: alerts = [] } = useAlerts();

  const activeAlerts = (alerts as any[]).filter((a) => !dismissedAlertIds.has(a.id));

  const matches = useMatches();
  const currentMatch = matches[matches.length - 1];
  const handle = (currentMatch?.handle as RouteHandle) || {};
  const pageTitle = handle.title || "VizenLink NVR";
  const isFullBleed = Boolean(handle.fullBleed);

  return (
    <TooltipProvider delayDuration={0}>
      <SidebarProvider open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <ThemeSync />
        <div className="flex min-h-dvh w-full">
        <AppSidebar />
        <SidebarInset className="flex flex-1 flex-col min-w-0">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4">
            <div className="flex items-center gap-2 min-w-0">
              <SidebarTrigger />
              <Link
                to="/"
                className="flex items-center md:hidden"
                aria-label="VizenLink NVR, go to Live"
              >
                <BrandLogo variant="mark" />
              </Link>
              <h1 className="text-xl font-semibold leading-[1.2] truncate">
                {pageTitle}
              </h1>
            </div>

            <div className="flex items-center gap-4">
              <ViewModeToggle />
              <UserMenu />
            </div>
          </header>

          <AlertsBanner alerts={activeAlerts} onDismiss={dismissAlert} />

          <main
            id="main"
            className={cn(
              "flex-1 overflow-auto",
              isFullBleed ? "p-2" : "p-4 md:p-6"
            )}
          >
            {isFullBleed ? (
              <Outlet />
            ) : (
              <div className="max-w-320 mx-auto w-full">
                <Outlet />
              </div>
            )}
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  </TooltipProvider>
  );
};

export default AppShell;
