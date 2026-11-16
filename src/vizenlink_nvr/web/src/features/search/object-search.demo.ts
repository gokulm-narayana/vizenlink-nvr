import type { ObjectDetection } from "./object-search";

export const SAMPLE_CAMERAS: Readonly<Record<string, string>> = {
  entrance: "Demo entrance",
  parking: "Demo parking",
  loading: "Demo loading bay",
};

export const SAMPLE_DETECTIONS: readonly ObjectDetection[] = [
  {
    id: "demo-person-1", cameraId: "entrance", timestamp: "2026-11-10T10:45:00Z",
    category: "People", objectType: "Person", clothing: { Shirt: "Red", Pants: "Black" },
    dwellSeconds: 42, confidence: 96,
  },
  {
    id: "demo-car", cameraId: "parking", timestamp: "2026-11-10T10:38:00Z",
    category: "Vehicles", objectType: "Car", color: "White", licensePlate: "DEMO 042",
    speedKmh: 12, dwellSeconds: 18, confidence: 94,
  },
  {
    id: "demo-bag", cameraId: "entrance", timestamp: "2026-11-10T10:31:00Z",
    category: "Bags", objectType: "Backpack", color: "Blue", dwellSeconds: 75, confidence: 91,
  },
  {
    id: "demo-vest", cameraId: "loading", timestamp: "2026-11-10T10:24:00Z",
    category: "Protective gear", objectType: "Safety vest", color: "Yellow", confidence: 98,
  },
  {
    id: "demo-person-2", cameraId: "loading", timestamp: "2026-11-10T10:20:00Z",
    category: "People", objectType: "Person", clothing: { Shirt: "Blue", Hat: "White" },
    protectiveGear: ["Hard hat", "Safety vest"], dwellSeconds: 12, confidence: 89,
  },
  {
    id: "demo-truck", cameraId: "loading", timestamp: "2026-11-10T10:12:00Z",
    category: "Vehicles", objectType: "Truck", color: "Red", licensePlate: "DEMO 105",
    speedKmh: 7, dwellSeconds: 60, confidence: 97,
  },
  {
    id: "demo-helmet", cameraId: "loading", timestamp: "2026-11-10T10:05:00Z",
    category: "Protective gear", objectType: "Hard hat", color: "White", confidence: 92,
  },
  {
    id: "demo-smoke", cameraId: "loading", timestamp: "2026-11-10T09:52:00Z",
    category: "Site hazards", objectType: "Smoke", dwellSeconds: 20, confidence: 88,
  },
];
