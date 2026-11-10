import { Link } from "react-router";
import { Cctv, HardDrive, Users, Smartphone, User, Activity, ChevronRight, Sun, Moon, Monitor } from "lucide-react";
import { useCurrentUser } from "@/lib/queries";
import { useUiStore, type Theme } from "@/stores/ui";
import { Button } from "@/components/ui/button";

export function SettingsPage() {
  const user = useCurrentUser();
  const theme = useUiStore(s => s.theme);
  const setTheme = useUiStore(s => s.setTheme);
  const manager = user?.role === "owner" || user?.role === "operator";
  const items = [
    { title: "Cameras", detail: "Add cameras, change names, and adjust picture and video settings.", path: "/cameras", icon: Cctv, visible: manager },
    { title: "Recording & Storage", detail: "Recording modes, weekly schedules, audio, and footage retention.", path: "/settings/recording", icon: HardDrive, visible: manager },
    { title: "Users & Access", detail: "Invite users and choose which cameras they can access.", path: "/users", icon: Users, visible: user?.role === "owner" },
    { title: "Mobile devices", detail: "Pair a phone or remove a device's remote access.", path: "/devices", icon: Smartphone, visible: user?.role === "owner" },
    { title: "System Health", detail: "View storage capacity, camera issues, and connection history.", path: "/dashboard", icon: Activity, visible: true },
    { title: "My Account", detail: "View your profile and update your password.", path: "/profile", icon: User, visible: true },
  ];
  return <div className="flex flex-col gap-6">
    <div className="grid gap-4 md:grid-cols-2">{items.filter(i => i.visible).map(item => <Link key={item.path} to={item.path} className="group flex items-start gap-4 rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary focus-visible:ring-2 focus-visible:ring-primary"><div className="rounded-lg bg-selected p-3 text-primary"><item.icon className="size-6" /></div><div className="flex-1"><h2 className="font-semibold">{item.title}</h2><p className="mt-1 text-sm text-muted-foreground">{item.detail}</p></div><ChevronRight className="mt-3 size-4 text-muted-foreground" /></Link>)}</div>
    <section className="rounded-xl border border-border bg-card p-5"><h2 className="font-semibold">Appearance</h2><p className="mb-4 mt-1 text-sm text-muted-foreground">Choose a comfortable theme for this screen.</p><div className="flex flex-wrap gap-3">{([{ value: "light", title: "Light", icon: Sun }, { value: "dark", title: "Dark", icon: Moon }, { value: "system", title: "Match device", icon: Monitor }] as const).map(t => <Button key={t.value} variant={theme === t.value ? "default" : "outline"} aria-pressed={theme === t.value} onClick={() => setTheme(t.value as Theme)}><t.icon className="size-4" />{t.title}</Button>)}</div></section>
  </div>;
}
