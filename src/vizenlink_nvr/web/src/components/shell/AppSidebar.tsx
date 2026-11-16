import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { SystemInfo } from "@/features/settings/SystemSettings";
import React from "react";
import { NavLink, Link, useLocation } from "react-router";
import {
  LayoutDashboard,
  LayoutGrid,
  History,
  Bell,
  Images,
  Cctv,
  Settings,
  Search,
  Sparkles,
  ArrowUpRight,
  Maximize,
} from "lucide-react";
import { cn } from "cn";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { BrandLogo } from "@/components/BrandLogo";
import { Kbd } from "@/components/ui/kbd";
import { useCurrentUser, useAlerts, useUnreadCount } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { isRegistered, type Role } from "@/app/routes";
import { RecorderStatusChip } from "./RecorderStatusChip";
import { WALL_PATH, enterPageFullscreen } from "@/lib/fullscreen";

interface NavItem {
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  minRole: Role;
  shortcut?: string;
  /** Opens Live View in full screen, with no header or sidebar. */
  wall?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const ROLE_RANKS: Record<string, number> = {
  viewer: 0,
  operator: 1,
  owner: 2,
};

function hasRole(userRole: string | undefined, minRole: Role): boolean {
  const current = ROLE_RANKS[userRole || "viewer"] ?? 0;
  const min = ROLE_RANKS[minRole] ?? 0;
  return current >= min;
}

// Phase 10: one flat menu in the old VMS order and naming
// (Dashboard, Cameras, Alerts, Multiview, Playback, Gallery, Settings).
const NAV_GROUPS: NavGroup[] = [
  {
    label: "Monitor",
    items: [
      { title: "Dashboard", path: "/", icon: LayoutDashboard, minRole: "viewer", shortcut: "G then D" },
      { title: "Cameras", path: "/cameras", icon: Cctv, minRole: "operator" },
      { title: "Live View", path: "/live", icon: LayoutGrid, minRole: "viewer", shortcut: "G then L" },
      { title: "Full screen view", path: "/live", icon: Maximize, minRole: "viewer", wall: true },
    ],
  },
  {
    label: "Investigate",
    items: [
      { title: "Search", path: "/search", icon: Search, minRole: "viewer", shortcut: "G then S" },
      { title: "Alerts", path: "/events", icon: Bell, minRole: "viewer", shortcut: "G then E" },
      { title: "Playback", path: "/playback", icon: History, minRole: "viewer", shortcut: "G then P" },
      { title: "Gallery", path: "/gallery", icon: Images, minRole: "viewer", shortcut: "G then G" },
      { title: "AI Assistant", path: "/assistant", icon: Sparkles, minRole: "viewer" },
    ],
  },
  {
    label: "Manage",
    items: [
      { title: "Settings", path: "/settings", icon: Settings, minRole: "viewer" },
    ],
  },
];

export const AppSidebar: React.FC = () => {
  const currentUser = useCurrentUser();
  const location = useLocation();
  const system = useQuery({ queryKey: ["system"], queryFn: () => apiFetch<SystemInfo>("/api/v1/system"), staleTime: 60000 });
  const recorderName = system.data?.recorder_name || "VizenLink NVR";
  const { state, isMobile, setOpenMobile } = useSidebar();
  const isCollapsed = state === "collapsed" && !isMobile;

  const { data: rawAlerts = [] } = useAlerts();
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const activeAlerts = (rawAlerts as any[]).filter((a) => !dismissedAlertIds.has(a.id));
  const activeAlertCount = activeAlerts.length;
  const hasCriticalAlert = activeAlerts.some((a) => a.severity === "critical");

  const { unreadCount = 0 } = useUnreadCount();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-16 justify-center border-b border-border p-0">
        {isCollapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                to="/"
                className="flex h-14 w-full items-center justify-center"
                aria-label={`${recorderName}, go to Dashboard`}
              >
                <BrandLogo variant="mark" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">{recorderName}</TooltipContent>
          </Tooltip>
        ) : (
          <Link
            to="/"
            className="flex h-14 min-w-0 flex-col items-start justify-center px-4"
            aria-label={`${recorderName}, go to Dashboard`}
          >
            <BrandLogo variant="lockup" />
            {recorderName !== "VizenLink NVR" && <span className="max-w-full truncate text-xs text-muted-foreground">{recorderName}</span>}
          </Link>
        )}
      </SidebarHeader>

      <SidebarContent>
        <nav aria-label="Primary" className="flex flex-col gap-2">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter(
              (item) => hasRole(currentUser?.role, item.minRole) && isRegistered(item.path)
            );

            if (visibleItems.length === 0) {
              return null;
            }

            return (
              <SidebarGroup key={group.label} className="p-2">
                {!isCollapsed && <SidebarGroupLabel className="px-4">{group.label}</SidebarGroupLabel>}
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visibleItems.map((item) => {
                      const targetPath = item.wall ? WALL_PATH : item.path;
                      // Active state is computed here and passed to SidebarMenuButton: with asChild,
                      // a NavLink className *function* was being stringified into every link's classes
                      // (all items rendered in the accent colour).
                      const path = location.pathname;
                      const isActive = item.wall
                        ? false
                        : item.path === "/"
                          ? path === "/" || path === "/dashboard"
                          : path === item.path || path.startsWith(item.path + "/");

                      const isDashboard = item.path === "/";
                      const showDashboardBadge = isDashboard && activeAlertCount > 0;

                      const isEvents = item.path === "/events";
                      const showEventsBadge = isEvents && unreadCount > 0;

                      let tooltipLabel = item.title;
                      if (showDashboardBadge) {
                        tooltipLabel = `${item.title} (${activeAlertCount} active alerts)`;
                      } else if (showEventsBadge) {
                        tooltipLabel = `${item.title} (${unreadCount} unread)`;
                      }

                      const tooltipContent = {
                        children: (
                          <div className="flex items-center gap-2">
                            <span>{tooltipLabel}</span>
                            {item.shortcut && <Kbd>{item.shortcut}</Kbd>}
                          </div>
                        ),
                      };

                      return (
                        <SidebarMenuItem key={item.title} className={isCollapsed ? "flex justify-center" : undefined}>
                          <SidebarMenuButton asChild isActive={isActive} tooltip={tooltipContent}
                            className={isCollapsed ? "justify-center" : undefined}>
                            <NavLink
                              to={targetPath}
                              end={targetPath === "/"}
                              onClick={() => {
                                if (isMobile) setOpenMobile(false);
                                // Asked for here because browsers only allow full screen from a click.
                                if (item.wall) enterPageFullscreen();
                              }}
                              aria-current={isActive ? "page" : undefined}
                              aria-label={isCollapsed ? tooltipLabel : undefined}
                              className="relative flex items-center gap-2"
                            >
                              <item.icon className="h-4 w-4 shrink-0" />
                              {!isCollapsed && <span>{item.title}</span>}
                              {!isCollapsed && showDashboardBadge && (
                                <span
                                  data-slot="dashboard-alert-badge"
                                  className={cn(
                                    "ml-auto flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums",
                                    hasCriticalAlert
                                      ? "bg-critical text-critical-foreground"
                                      : "bg-warning text-warning-foreground"
                                  )}
                                >
                                  {activeAlertCount > 99 ? "99+" : activeAlertCount}
                                </span>
                              )}
                              {!isCollapsed && showEventsBadge && (
                                <span
                                  data-slot="events-unread-badge"
                                  className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums bg-primary text-primary-foreground"
                                >
                                  {unreadCount > 99 ? "99+" : unreadCount}
                                </span>
                              )}
                            </NavLink>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            );
          })}
        </nav>
      </SidebarContent>

      <SidebarFooter className="border-t border-border p-2">
        {!isCollapsed && <Link to="/assistant" onClick={() => { if (isMobile) setOpenMobile(false); }} className="sidebar-assistant-card mb-2 flex items-center gap-2 rounded-xl border border-border p-4"><Sparkles className="size-5 shrink-0 text-primary" /><span className="min-w-0 flex-1"><span className="block text-sm font-semibold">A little help?</span><span className="block text-xs text-muted-foreground">Ask your recorder</span></span><ArrowUpRight className="size-4 text-muted-foreground" /></Link>}
        <RecorderStatusChip />
      </SidebarFooter>
    </Sidebar>
  );
};

export default AppSidebar;
