import React from "react";
import { Link, Outlet, useMatches } from "react-router";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppSidebar } from "./AppSidebar";
import { UserMenu } from "./UserMenu";
import { AlertsBell } from "./AlertsBell";
import { AlertStack } from "./AlertStack";
import { RefetchBar } from "./RefetchBar";
import { Shortcuts } from "./Shortcuts";
import { ThemeSync } from "./ThemeSync";
import { ThemeToggle } from "./ThemeToggle";
import { BrandLogo } from "@/components/BrandLogo";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";
import { Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorkspaceSearch } from "./WorkspaceSearch";
import { useWallFullscreenGuard } from "@/lib/fullscreen";

interface RouteHandle {
  title?: string;
  fullBleed?: boolean;
  stickyContent?: boolean;
}

export const AppShell: React.FC = () => {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);

  useWallFullscreenGuard();
  const matches = useMatches();
  const currentMatch = matches[matches.length - 1];
  const handle = (currentMatch?.handle as RouteHandle) || {};
  const pageTitle = handle.title || "VizenLink NVR";
  const isFullBleed = Boolean(handle.fullBleed);

  return (
    <TooltipProvider delayDuration={0}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-foreground focus:ring-2 focus:ring-primary shadow-md"
      >
        Skip to main content
      </a>
      <Shortcuts />
      <SidebarProvider open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <ThemeSync />
        <div className="flex min-h-dvh w-full">
        <AppSidebar />
        <SidebarInset className="flex flex-1 flex-col min-w-0">
          <header className="workspace-header sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-4 md:px-6">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <SidebarTrigger />
              <Link
                to="/"
                className="flex items-center md:hidden"
                aria-label="VizenLink NVR, go to Dashboard"
              >
                <BrandLogo variant="mark" />
              </Link>
              <h1 className="text-xl font-semibold leading-[1.2] truncate">
                {pageTitle}
              </h1>
            </div>

            <div className="flex shrink-0 items-center gap-1 sm:gap-2">
              <WorkspaceSearch />
              <Button variant="ghost" size="icon" className="workspace-search-link" aria-label="Search footage" asChild><Link to="/search"><Search className="size-4" /></Link></Button>
              <Button variant="ghost" size="icon" className="hidden sm:inline-flex" aria-label="Open AI assistant" asChild><Link to="/assistant"><Sparkles className="size-4" /></Link></Button>
              <AlertsBell />
              <ThemeToggle />
              <UserMenu />
            </div>
            <RefetchBar />
          </header>

          <AlertStack />

          <main
            id="main"
            tabIndex={-1}
            className={cn(
              "flex-1 outline-hidden",
              handle.stickyContent ? "overflow-x-clip" : "overflow-auto",
              isFullBleed ? "p-2" : "p-4 md:p-6"
            )}
          >
            {isFullBleed ? (
              <Outlet />
            ) : (
              <div className="w-full">
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
