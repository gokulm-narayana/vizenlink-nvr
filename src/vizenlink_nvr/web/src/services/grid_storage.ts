/**
 * Multiview grid layout localStorage persistence (LIVE-06).
 */

export type GridDimension = 1 | 2 | 3 | 4;

export interface GridPersistenceData {
  dimension: GridDimension;
  page: number;
  slotAssignments: Record<number, string>;
}

const STORAGE_KEY = "vizenlink_nvr_grid_layout_v1";

export class GridStorage {
  public static load(defaultDimension: GridDimension = 2): GridPersistenceData {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { dimension: defaultDimension, page: 0, slotAssignments: {} };
      }
      const parsed = JSON.parse(raw);
      const dim = [1, 2, 3, 4].includes(parsed.dimension) ? parsed.dimension : defaultDimension;
      const page = typeof parsed.page === "number" && parsed.page >= 0 ? parsed.page : 0;
      const slotAssignments = parsed.slotAssignments && typeof parsed.slotAssignments === "object"
        ? parsed.slotAssignments
        : {};
      return { dimension: dim as GridDimension, page, slotAssignments };
    } catch {
      return { dimension: defaultDimension, page: 0, slotAssignments: {} };
    }
  }

  public static save(data: GridPersistenceData): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // Ignore quota errors in private browsing
    }
  }

  public static clear(): void {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore
    }
  }
}

