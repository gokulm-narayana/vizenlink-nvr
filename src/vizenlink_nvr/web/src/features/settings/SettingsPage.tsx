import type { ComponentType, ReactNode } from "react";
import { NavLink } from "react-router";
import { Disc, HardDrive, ScrollText, Settings2, Smartphone, Sparkles, User, Users } from "lucide-react";
import { useCurrentUser } from "@/lib/queries";
import { SystemSettings } from "./SystemSettings";

type Section = { path: string; title: string; icon: ComponentType<{ className?: string }>; visible: boolean };

export function SettingsPage({ children }: { children?: ReactNode }) {
  const role = useCurrentUser()?.role;
  const manager = role === "owner" || role === "operator";
  const owner = role === "owner";
  const groups: Array<{ label: string; sections: Section[] }> = [
    {
      label: "Recorder",
      sections: [
        { path: "/settings", title: "System", icon: Settings2, visible: true },
        { path: "/settings/recording", title: "Recording", icon: Disc, visible: manager },
        { path: "/settings/storage", title: "Storage", icon: HardDrive, visible: manager },
        { path: "/settings/ai", title: "AI & API keys", icon: Sparkles, visible: owner },
      ],
    },
    {
      label: "Access",
      sections: [
        { path: "/settings/users", title: "Users", icon: Users, visible: owner },
        { path: "/settings/devices", title: "Mobile devices", icon: Smartphone, visible: owner },
        { path: "/settings/audit", title: "Audit log", icon: ScrollText, visible: owner },
      ],
    },
    { label: "You", sections: [{ path: "/profile", title: "My Account", icon: User, visible: true }] },
  ];
  return (
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6">
      {/* Phones: one scrolling row of pills. Wide screens: grouped menu that stays in view. */}
      <nav
        aria-label="Settings sections"
        className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-2 lg:sticky lg:top-0 lg:flex-col lg:gap-4 lg:overflow-visible lg:p-4"
      >
        {groups.map(group => {
          const visible = group.sections.filter(section => section.visible);
          if (!visible.length) return null;
          return (
            <div key={group.label} className="flex shrink-0 gap-1 lg:flex-col">
              <p className="hidden px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground lg:block">{group.label}</p>
              {visible.map(section => (
                <NavLink
                  key={section.path}
                  to={section.path}
                  end
                  className={({ isActive }) =>
                    `flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-2 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      isActive ? "bg-selected font-semibold text-selected-foreground" : "text-foreground hover:bg-muted"
                    }`
                  }
                >
                  <section.icon className="size-4 shrink-0" aria-hidden />
                  {section.title}
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="flex min-w-0 flex-col gap-4 lg:gap-6">{children ?? <SystemSettings />}</div>
    </div>
  );
}
