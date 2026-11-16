import { NativeSelect } from "@/components/ui/native-select";
import { useState } from "react";
import { Link } from "react-router";
import { ArrowLeft, Backpack, Car, Clock, HardHat, Search, TriangleAlert, UserRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageIntro } from "@/components/PageIntro";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { CLOTHING, filterDetections, OBJECT_COLORS, OBJECT_TYPES, type ObjectCategory, type ObjectFilters } from "./object-search";
import { SAMPLE_CAMERAS, SAMPLE_DETECTIONS } from "./object-search.demo";

const EMPTY_FILTERS: ObjectFilters = {
  category: "", objectType: "", color: "", clothingItem: "", protectiveGear: "",
  licensePlate: "", cameraId: "", minimumDwell: "", minimumSpeed: "", minimumConfidence: "",
};

const CATEGORY_ICONS = {
  People: UserRound,
  Vehicles: Car,
  Bags: Backpack,
  "Protective gear": HardHat,
  "Site hazards": TriangleAlert,
};
const CATEGORIES = Object.keys(OBJECT_TYPES) as ObjectCategory[];
const COLORS = Object.keys(OBJECT_COLORS) as Array<keyof typeof OBJECT_COLORS>;

function Choice<T extends string>({ label, emptyLabel, options, value, onChange }: {
  label: string;
  emptyLabel: string;
  options: readonly T[];
  value: T | "";
  onChange: (value: T | "") => void;
}) {
  return (
    <label className="vms-field">
      {label}
      <NativeSelect className="w-full" value={value} onChange={e => onChange(e.target.value as T | "")}>
        <option value="">{emptyLabel}</option>
        {options.map(option => <option key={option}>{option}</option>)}
      </NativeSelect>
    </label>
  );
}

export function ObjectSearchPreview({ footageUrl }: { footageUrl: string }) {
  const zone = useSiteTimeZone();
  const [filters, setFilters] = useState<ObjectFilters>(EMPTY_FILTERS);
  const results = filterDetections(SAMPLE_DETECTIONS, filters);
  const set = <K extends keyof ObjectFilters>(key: K, value: ObjectFilters[K]) =>
    setFilters(current => ({ ...current, [key]: value }));

  function chooseCategory(category: ObjectFilters["category"]) {
    setFilters(current => ({
      ...current, category, objectType: "", clothingItem: "", protectiveGear: "", licensePlate: "", minimumSpeed: "",
    }));
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold">Object Search</h2>
      <PageIntro
        description="Preview filters using sample detections. The results below are synthetic and have no associated footage."
        actions={<Button asChild variant="outline"><Link to={footageUrl}><ArrowLeft />Back to footage search</Link></Button>}
      />
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex flex-wrap gap-2 border-b border-border p-4" role="group" aria-label="Object category">
          <Button variant={filters.category ? "ghost" : "secondary"} aria-pressed={!filters.category} onClick={() => chooseCategory("")}>
            <Search />All objects
          </Button>
          {CATEGORIES.map(category => {
            const Icon = CATEGORY_ICONS[category];
            const selected = filters.category === category;
            return <Button key={category} variant={selected ? "secondary" : "ghost"} aria-pressed={selected} onClick={() => chooseCategory(category)}>
              <Icon />{category}
            </Button>;
          })}
        </div>

        <div className="flex flex-col lg:flex-row">
          <aside className="search-filter-panel flex min-w-0 flex-col gap-4 border-b border-border p-4 lg:w-80 lg:shrink-0 lg:border-r lg:border-b-0" aria-label="Object filters">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Filters</h3>
              <Button variant="ghost" size="sm" onClick={() => setFilters(EMPTY_FILTERS)}>Reset filters</Button>
            </div>

            {filters.category && <Choice label="Object type" emptyLabel="Any type" options={OBJECT_TYPES[filters.category]}
              value={filters.objectType} onChange={value => set("objectType", value)} />}
            {filters.category === "People" && <>
              <Choice label="Clothing" emptyLabel="Any clothing" options={CLOTHING}
                value={filters.clothingItem} onChange={value => set("clothingItem", value)} />
              <Choice label="Worn protective gear" emptyLabel="Any gear" options={OBJECT_TYPES["Protective gear"]}
                value={filters.protectiveGear} onChange={value => set("protectiveGear", value)} />
            </>}
            {filters.category === "Vehicles" && <label className="vms-field">
              License plate<Input placeholder="e.g. DEMO 042" value={filters.licensePlate} onChange={e => set("licensePlate", e.target.value)} />
            </label>}

            <fieldset className="min-w-0">
              <legend className="mb-2 text-sm">Color</legend>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant={filters.color ? "outline" : "secondary"} aria-pressed={!filters.color} onClick={() => set("color", "")}>Any</Button>
                {COLORS.map(color => <Button key={color} size="sm" variant={filters.color === color ? "secondary" : "outline"}
                  aria-pressed={filters.color === color} onClick={() => set("color", color)}>
                  <span aria-hidden="true" className="size-3 shrink-0 rounded-full border border-border"
                    // dynamic-style: show the swatch for this color filter.
                    style={{ backgroundColor: OBJECT_COLORS[color] }} />{color}
                </Button>)}
              </div>
            </fieldset>

            <label className="vms-field">
              Sample camera
              <NativeSelect className="w-full" value={filters.cameraId} onChange={e => set("cameraId", e.target.value)}>
                <option value="">All sample cameras</option>
                {Object.entries(SAMPLE_CAMERAS).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </NativeSelect>
            </label>

            <label className="vms-field">
              Minimum dwell time (seconds)
              <Input type="number" min={0} value={filters.minimumDwell} onChange={e => set("minimumDwell", e.target.value === "" ? "" : e.target.valueAsNumber)} />
            </label>
            {filters.category === "Vehicles" && <label className="vms-field">
              Minimum speed (km/h)
              <Input type="number" min={0} value={filters.minimumSpeed} onChange={e => set("minimumSpeed", e.target.value === "" ? "" : e.target.valueAsNumber)} />
            </label>}
            <label className="vms-field">
              Minimum confidence (%)
              <Input type="number" min={0} max={100} value={filters.minimumConfidence} onChange={e => set("minimumConfidence", e.target.value === "" ? "" : e.target.valueAsNumber)} />
            </label>
          </aside>

          <section className="flex min-w-0 flex-1 flex-col gap-4 p-4" aria-label="Sample detections">
            <p className="text-sm text-muted-foreground" role="status">
              {results.length} sample {results.length === 1 ? "detection" : "detections"}
            </p>
            {results.length === 0 && <p className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">No sample detections match these filters.</p>}
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {results.map(detection => {
                const Icon = CATEGORY_ICONS[detection.category];
                return <li key={detection.id} className="flex min-w-0 flex-col gap-4 rounded-lg border border-border p-4">
                  <div className="flex items-center gap-2">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-selected text-selected-foreground"><Icon className="size-4" /></span>
                    <div className="min-w-0">
                      <h3 className="font-semibold">{detection.objectType}</h3>
                      <p className="text-xs text-muted-foreground">{SAMPLE_CAMERAS[detection.cameraId]}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {detection.color && <Badge variant="secondary">{detection.color}</Badge>}
                    {Object.entries(detection.clothing ?? {}).map(([item, color]) => <Badge key={item} variant="secondary">{color} {item.toLowerCase()}</Badge>)}
                    {detection.protectiveGear?.map(gear => <Badge key={gear} variant="outline">{gear}</Badge>)}
                    {detection.licensePlate && <Badge variant="outline">{detection.licensePlate}</Badge>}
                    {detection.dwellSeconds !== undefined && <Badge variant="outline">{detection.dwellSeconds}s dwell</Badge>}
                    {detection.speedKmh !== undefined && <Badge variant="outline">{detection.speedKmh} km/h</Badge>}
                    {detection.confidence !== undefined && <Badge variant="outline">{detection.confidence}% confidence</Badge>}
                  </div>
                  <p className="mt-auto flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="size-4 shrink-0" />{formatDateTime(detection.timestamp, zone)}
                  </p>
                </li>;
              })}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
