import React from "react";
import { NavLink, Link } from "react-router";
import {
  LayoutGrid,
  History,
  Bell,
  Images,
  Activity,
  Cctv,
  Users,
  Smartphone,
} from "lucide-react";
import { cn } from "cn";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
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
import { useCurrentUser } from "@/lib/queries";
import { isRegistered, type Role } from "@/app/routes";

interface NavItem {
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  minRole: Role;
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
    label: "Watch",
    items: [
      { title: "Live", path: "/live", icon: LayoutGrid, minRole: "viewer" },
      { title: "Playback", path: "/playback", icon: History, minRole: "viewer" },
      { title: "Events", path: "/events", icon: Bell, minRole: "viewer" },
      { title: "Gallery", path: "/gallery", icon: Images, minRole: "viewer" },
    ],
  },
  {
    label: "Monitor",
    items: [
      { title: "Dashboard", path: "/dashboard", icon: Activity, minRole: "viewer" },
    ],
  },
  {
    label: "Manage",
    items: [
      { title: "Cameras", path: "/cameras", icon: Cctv, minRole: "operator" },
      { title: "Users", path: "/users", icon: Users, minRole: "owner" },
      { title: "Mobile devices", path: "/devices", icon: Smartphone, minRole: "owner" },
    ],
  },
];

export const AppSidebar: React.FC = () => {
  const currentUser = useCurrentUser();
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

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
                    {visibleItems.map((item) => (
                      <SidebarMenuItem key={item.path}>
                        <SidebarMenuButton asChild tooltip={item.title}>
                          <NavLink
                            to={item.path}
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
                          </NavLink>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            );
          })}
        </nav>
      </SidebarContent>
    </Sidebar>
  );
};

export default AppSidebar;
