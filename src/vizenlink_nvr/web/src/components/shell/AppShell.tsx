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
import { BrandLogo } from "@/components/BrandLogo";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";

interface RouteHandle {
  title?: string;
  fullBleed?: boolean;
}

export const AppShell: React.FC = () => {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);

  const matches = useMatches();
  const currentMatch = matches[matches.length - 1];
  const handle = (currentMatch?.handle as RouteHandle) || {};
  const pageTitle = handle.title || "VizenLink NVR";
  const isFullBleed = Boolean(handle.fullBleed);
  const descriptions: Record<string, string> = {
    "Live View": "Your cameras, together. Choose a view or find a camera to get started.",
    Playback: "Find a moment, review the footage, and save what matters.",
    Events: "Review detections and jump straight to the recorded moment.",
    "Saved Media": "Your saved snapshots and exported video clips, in one place.",
    "System Health": "Check camera connections, storage, and issues that need attention.",
    Cameras: "Choose a camera to update its picture, video, or connection settings.",
    Users: "Manage who can access your recorder and which cameras they can see.",
    "Mobile devices": "Connect your phone and manage devices with remote access.",
    Profile: "Manage your account and sign-in details.",
    Settings: "Set up your cameras, recording preferences, and access.",
    "Recording & Storage": "Choose when to record and how long to keep footage.",
  };

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
          <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4">
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

            <div className="flex items-center gap-2">
              <AlertsBell />

              <UserMenu />
            </div>
            <RefetchBar />
          </header>

          <AlertStack />

          <main
            id="main"
            tabIndex={-1}
            className={cn(
              "flex-1 overflow-auto outline-hidden",
              isFullBleed ? "p-2" : "p-4 md:p-6"
            )}
          >
            {isFullBleed ? (
              <Outlet />
            ) : (
              <div className="max-w-320 mx-auto w-full">
                {descriptions[pageTitle] && <p className="mb-6 text-sm text-muted-foreground">{descriptions[pageTitle]}</p>}
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
