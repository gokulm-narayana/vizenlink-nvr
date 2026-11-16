export const OBJECT_TYPES = {
  People: ["Person"],
  Vehicles: ["Car", "Motorcycle", "Bicycle", "Bus", "Truck", "Van", "Autorickshaw"],
  Bags: ["Backpack", "Handbag", "Suitcase", "Parcel", "Tool bag"],
  "Protective gear": ["Helmet", "Safety vest", "Hard hat", "Mask", "Respirator"],
  "Site hazards": ["Smoke", "Fire", "Spill", "Gas cylinder"],
} as const;

export const OBJECT_COLORS = {
  Red: "#dc2626",
  Blue: "#2563eb",
  Green: "#15803d",
  Yellow: "#facc15",
  Orange: "#f97316",
  Black: "#171717",
  White: "#ffffff",
  Silver: "#a3a3a3",
} as const;

export const CLOTHING = ["Shirt", "Pants", "Hat"] as const;

export type ObjectCategory = keyof typeof OBJECT_TYPES;
type ObjectType = (typeof OBJECT_TYPES)[ObjectCategory][number];
type ObjectColor = keyof typeof OBJECT_COLORS;
type ClothingItem = (typeof CLOTHING)[number];
type GearType = (typeof OBJECT_TYPES)["Protective gear"][number];

export interface ObjectDetection {
  id: string;
  cameraId: string;
  timestamp: string;
  category: ObjectCategory;
  objectType: ObjectType;
  color?: ObjectColor;
  clothing?: Partial<Record<ClothingItem, ObjectColor>>;
  protectiveGear?: readonly GearType[];
  licensePlate?: string;
  dwellSeconds?: number;
  speedKmh?: number;
  confidence?: number;
}

export interface ObjectFilters {
  category: ObjectCategory | "";
  objectType: ObjectType | "";
  color: ObjectColor | "";
  clothingItem: ClothingItem | "";
  protectiveGear: GearType | "";
  licensePlate: string;
  cameraId: string;
  minimumDwell: number | "";
  minimumSpeed: number | "";
  minimumConfidence: number | "";
}

function normalizePlate(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function filterDetections(detections: readonly ObjectDetection[], filters: ObjectFilters): ObjectDetection[] {
  const plate = normalizePlate(filters.licensePlate);
  return detections.filter(detection => {
    const clothingColor = filters.clothingItem ? detection.clothing?.[filters.clothingItem] : undefined;
    const matchesColor = filters.clothingItem
      ? clothingColor !== undefined && (!filters.color || clothingColor === filters.color)
      : !filters.color || detection.color === filters.color || Object.values(detection.clothing ?? {}).includes(filters.color);
    return (!filters.category || detection.category === filters.category)
      && (!filters.objectType || detection.objectType === filters.objectType)
      && (!filters.cameraId || detection.cameraId === filters.cameraId)
      && matchesColor
      && (!filters.protectiveGear || detection.protectiveGear?.includes(filters.protectiveGear))
      && (!plate || normalizePlate(detection.licensePlate ?? "").includes(plate))
      && (filters.minimumDwell === "" || (detection.dwellSeconds ?? -1) >= filters.minimumDwell)
      && (filters.minimumSpeed === "" || (detection.speedKmh ?? -1) >= filters.minimumSpeed)
      && (filters.minimumConfidence === "" || (detection.confidence ?? -1) >= filters.minimumConfidence);
  });
}
