import { describe, it, expect, beforeEach, vi } from "vitest";
import { GridStorage, type GridPersistenceData } from "./grid_storage";

describe("GridStorage", () => {
  const STORAGE_KEY = "vizenlink_nvr_grid_layout_v1";

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("writes and reads exactly the key vizenlink_nvr_grid_layout_v1", () => {
    const payload: GridPersistenceData = {
      dimension: 3,
      page: 1,
      slotAssignments: { 0: "CAM_FRONT", 1: "CAM_BACK" },
    };

    GridStorage.save(payload);

    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!)).toEqual(payload);

    const loaded = GridStorage.load();
    expect(loaded).toEqual(payload);
  });

  it("loads legacy app saved payload unchanged", () => {
    const legacyJson = JSON.stringify({
      dimension: 4,
      page: 2,
      slotAssignments: { 0: "CAM1", 5: "CAM6" },
    });
    localStorage.setItem(STORAGE_KEY, legacyJson);

    const loaded = GridStorage.load();
    expect(loaded.dimension).toBe(4);
    expect(loaded.page).toBe(2);
    expect(loaded.slotAssignments).toEqual({ 0: "CAM1", 5: "CAM6" });
  });

  it("falls back to defaults when storage is missing", () => {
    const loaded = GridStorage.load(3);
    expect(loaded.dimension).toBe(3);
    expect(loaded.page).toBe(0);
    expect(loaded.slotAssignments).toEqual({});
  });

  it("falls back to defaults on malformed JSON", () => {
    localStorage.setItem(STORAGE_KEY, "invalid-json{");

    const loaded = GridStorage.load(2);
    expect(loaded.dimension).toBe(2);
    expect(loaded.page).toBe(0);
    expect(loaded.slotAssignments).toEqual({});
  });

  it("falls back to defaults on invalid dimension or negative page", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ dimension: 5, page: -1, slotAssignments: "invalid" })
    );

    const loaded = GridStorage.load(2);
    expect(loaded.dimension).toBe(2);
    expect(loaded.page).toBe(0);
    expect(loaded.slotAssignments).toEqual({});
  });

  it("does not throw on localStorage quota error during save", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError", "QuotaExceededError");
    });

    expect(() => {
      GridStorage.save({ dimension: 1, page: 0, slotAssignments: {} });
    }).not.toThrow();
  });

  it("clears storage when clear() is called", () => {
    GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull();

    GridStorage.clear();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
