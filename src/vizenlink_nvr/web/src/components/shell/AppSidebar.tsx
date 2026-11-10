import React from "react";
import { NavLink, Link, useLocation } from "react-router";
import {
  LayoutGrid,
  History,
  Bell,
  Images,
  Activity,
  Cctv,
  Users,
  Smartphone,
  Settings,
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

interface NavItem {
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  minRole: Role;
  shortcut?: string;
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

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Your workspace",
    items: [
      { title: "Live View", path: "/", icon: LayoutGrid, minRole: "viewer", shortcut: "G then L" },
      { title: "Playback", path: "/playback", icon: History, minRole: "viewer", shortcut: "G then P" },
      { title: "Events", path: "/events", icon: Bell, minRole: "viewer", shortcut: "G then E" },
      { title: "Saved Media", path: "/gallery", icon: Images, minRole: "viewer", shortcut: "G then G" },
    ],
  },
  {
    label: "Recorder",
    items: [
      { title: "System Health", path: "/dashboard", icon: Activity, minRole: "viewer", shortcut: "G then D" },
    ],
  },
  {
    label: "Manage",
    items: [
      { title: "Cameras", path: "/cameras", icon: Cctv, minRole: "operator" },
      { title: "Settings", path: "/settings", icon: Settings, minRole: "viewer" },
    ],
  },
];

export const AppSidebar: React.FC = () => {
  const currentUser = useCurrentUser();
  const location = useLocation();
  const { state, isMobile, setOpenMobile } = useSidebar();
  const isCollapsed = state === "collapsed";

  const { data: rawAlerts = [] } = useAlerts();
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const activeAlerts = (rawAlerts as any[]).filter((a) => !dismissedAlertIds.has(a.id));
  const activeAlertCount = activeAlerts.length;
  const hasCriticalAlert = activeAlerts.some((a) => a.severity === "critical");

  const { unreadCount = 0 } = useUnreadCount();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 justify-center border-b border-border p-0">
        {isCollapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                to="/"
                className="flex h-14 w-full items-center justify-center"
                aria-label="VizenLink NVR, go to Live"
              >
                <BrandLogo variant="mark" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">VizenLink NVR</TooltipContent>
          </Tooltip>
        ) : (
          <Link
            to="/"
            className="flex h-14 items-center px-4"
            aria-label="VizenLink NVR, go to Live"
          >
            <BrandLogo variant="lockup" />
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
                <SidebarGroupLabel className="text-xs font-normal">
                  {group.label}
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visibleItems.map((item) => {
                      const targetPath =
                        item.path === "/" && location.pathname === "/live"
                          ? "/live"
                          : item.path;

                      const isDashboard = item.path === "/dashboard";
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
                        <SidebarMenuItem key={item.path}>
                          <SidebarMenuButton asChild tooltip={tooltipContent}>
                            <NavLink
                              to={targetPath}
                              onClick={() => { if (isMobile) setOpenMobile(false); }}
                              className={({ isActive }) =>
                                cn(
                                  "relative flex items-center gap-2",
                                  isActive &&
                                    "bg-selected text-primary-text font-semibold before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:rounded-r before:bg-primary"
                                )
                              }
                            >
                              <item.icon className="h-4 w-4 shrink-0" />
                              <span>{item.title}</span>
                              {showDashboardBadge && (
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
                              {showEventsBadge && (
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
        <RecorderStatusChip />
      </SidebarFooter>
    </Sidebar>
  );
};

export default AppSidebar;
