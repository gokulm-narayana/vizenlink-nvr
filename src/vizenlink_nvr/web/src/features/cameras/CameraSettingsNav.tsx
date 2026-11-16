import { NativeSelect } from "@/components/ui/native-select";
import { Bell, Image as ImageIcon, Lock, Mic, Move, Network, RotateCcw, Siren, SlidersHorizontal, Type, UserCog, HardDrive, Activity, Info, Plug, Video } from "lucide-react";
import type { ComponentType } from "react";

/* One grouped menu for every camera settings section. Replaces the old dropdown + tab bar,
   which duplicated each other, used different names and each showed only some sections. */

export interface SettingsSection {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

export const SETTINGS_GROUPS: Array<{ title: string; sections: SettingsSection[] }> = [
  {
    title: "Picture",
    sections: [
      { id: "image", label: "Image & night mode", icon: ImageIcon },
      { id: "video", label: "Video quality", icon: Video },
      { id: "overlays", label: "On-screen text", icon: Type },
    ],
  },
  {
    title: "Detection & safety",
    sections: [
      { id: "detection", label: "Detection & alerts", icon: Bell },
      { id: "deterrence", label: "Siren & spotlight", icon: Siren },
      { id: "privacy", label: "Privacy", icon: Lock },
      { id: "movement", label: "Movement protection", icon: Move },
    ],
  },
  {
    title: "Sound",
    sections: [{ id: "audio", label: "Audio", icon: Mic }],
  },
  {
    title: "Device",
    sections: [
      { id: "identity", label: "Details", icon: Info },
      { id: "network", label: "Network", icon: Network },
      { id: "camera-storage", label: "Camera SD card", icon: HardDrive },
      { id: "accounts", label: "Camera accounts", icon: UserCog },
      { id: "connections", label: "Connection info", icon: Plug },
      { id: "health", label: "Health", icon: Activity },
      { id: "maintenance", label: "Reboot & reset", icon: RotateCcw },
    ],
  },
];

export const SETTINGS_SECTION_IDS = SETTINGS_GROUPS.flatMap(g => g.sections.map(s => s.id));

export function sectionLabel(id: string): string {
  return SETTINGS_GROUPS.flatMap(g => g.sections).find(s => s.id === id)?.label ?? id;
}

export function CameraSettingsNav({ active, onChange }: { active: string; onChange: (id: string) => void }) {
  return (
    // One wrapper = one grid item in the page layout.
    <div className="min-w-0">
      {/* Phones and narrow windows: one dropdown with the same groups. The wrapper carries
          lg:hidden because .vms-field sets its own display and would override it. */}
      <div className="lg:hidden">
      <label className="vms-field">
        <span className="flex items-center gap-2 font-semibold"><SlidersHorizontal className="size-4" />Settings section</span>
        <NativeSelect aria-label="Settings section" className="w-full" value={active} onChange={e => onChange(e.target.value)}>
          {SETTINGS_GROUPS.map(group => (
            <optgroup key={group.title} label={group.title}>
              {group.sections.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </optgroup>
          ))}
        </NativeSelect>
      </label>
      </div>

      {/* Wide screens: grouped vertical menu, every section visible at once. */}
      {/* Stays below the 4rem app header while the section on the right scrolls; scrolls on
          its own only if the window is too short for all sections. */}
      <nav aria-label="Camera settings" className="hidden h-full lg:block">
        <div role="tablist" aria-orientation="vertical" className="sticky top-20 flex max-h-[calc(100dvh-6rem)] flex-col gap-4 overflow-y-auto pb-4">
          {SETTINGS_GROUPS.map(group => (
            <div key={group.title} className="flex flex-col gap-1">
              <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.title}</p>
              {group.sections.map(s => {
                const selected = s.id === active;
                const Icon = s.icon;
                return (
                  <button
                    key={s.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    data-state={selected ? "active" : "inactive"}
                    onClick={() => onChange(s.id)}
                    className={`flex items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      selected ? "bg-selected font-semibold text-selected-foreground" : "text-foreground hover:bg-muted"
                    }`}
                  >
                    <Icon className="size-4 shrink-0" />
                    {s.label}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </nav>
    </div>
  );
}
