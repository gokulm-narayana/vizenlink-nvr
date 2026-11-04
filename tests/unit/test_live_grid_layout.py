"""Unit tests for live multiview grid layout calculation and pagination (LIVE-02)."""

from __future__ import annotations

import pytest

from vizenlink_nvr.services.live_view import GridLayoutCalculator


def test_grid_dimension_tiles_per_page() -> None:
    """Validate 1x1 to 4x4 tile capacities."""
    assert GridLayoutCalculator.get_tiles_per_page(1) == 1
    assert GridLayoutCalculator.get_tiles_per_page(2) == 4
    assert GridLayoutCalculator.get_tiles_per_page(3) == 9
    assert GridLayoutCalculator.get_tiles_per_page(4) == 16

    # Invalid dimensions reject with ValueError
    with pytest.raises(ValueError):
        GridLayoutCalculator.get_tiles_per_page(0)
    with pytest.raises(ValueError):
        GridLayoutCalculator.get_tiles_per_page(5)


def test_grid_total_pages_calculation() -> None:
    """Page count adjusts dynamically based on camera count and grid dimension."""
    # Empty camera set still has 1 empty page
    assert GridLayoutCalculator.get_total_pages(0, dimension=2) == 1

    # 4 cameras in 2x2 grid = 1 page
    assert GridLayoutCalculator.get_total_pages(4, dimension=2) == 1

    # 5 cameras in 2x2 grid = 2 pages
    assert GridLayoutCalculator.get_total_pages(5, dimension=2) == 2

    # 16 cameras in 4x4 grid = 1 page; 17 cameras = 2 pages
    assert GridLayoutCalculator.get_total_pages(16, dimension=4) == 1
    assert GridLayoutCalculator.get_total_pages(17, dimension=4) == 2

    # 25 cameras in 3x3 grid (9/page) = 3 pages (9 + 9 + 7)
    assert GridLayoutCalculator.get_total_pages(25, dimension=3) == 3


def test_grid_pagination_slicing() -> None:
    """Paginate slices exact subsets without overlapping or skipping."""
    cameras = [f"CAM-{i:02d}" for i in range(1, 11)]  # 10 cameras

    # In 2x2 (4 per page):
    page_0 = GridLayoutCalculator.paginate(cameras, dimension=2, page_index=0)
    assert page_0 == ["CAM-01", "CAM-02", "CAM-03", "CAM-04"]

    page_1 = GridLayoutCalculator.paginate(cameras, dimension=2, page_index=1)
    assert page_1 == ["CAM-05", "CAM-06", "CAM-07", "CAM-08"]

    page_2 = GridLayoutCalculator.paginate(cameras, dimension=2, page_index=2)
    assert page_2 == ["CAM-09", "CAM-10"]

    page_3 = GridLayoutCalculator.paginate(cameras, dimension=2, page_index=3)
    assert page_3 == []
