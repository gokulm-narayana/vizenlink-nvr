"""Contract tests validating OpenAPI 3.1 schema and breaking-change protection (MOB-01)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from vizenlink_nvr.api.app import app

_tools_path = Path(__file__).parents[2] / "tools" / "check_api_breaking_changes.py"
_spec = importlib.util.spec_from_file_location("check_api_breaking_changes", _tools_path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
find_breaking_changes = _mod.find_breaking_changes

BASELINE_PATH = Path(__file__).parents[2] / "contracts" / "openapi_v1_baseline.json"


def test_baseline_schema_exists_and_matches_app() -> None:
    """Verify that the committed OpenAPI baseline exists and the current app is compatible."""
    assert BASELINE_PATH.exists(), f"Missing baseline at {BASELINE_PATH}"
    baseline_json = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    current_json = app.openapi()
    assert current_json.get("openapi", "").startswith("3.1")
    assert "paths" in current_json

    violations = find_breaking_changes(baseline_json, current_json)
    assert not violations, f"Breaking changes detected: {violations}"


def test_breaking_change_detector_catches_incompatible_mutations() -> None:
    """Negative controls proving find_breaking_changes catches all classes of breaking changes."""
    base = {
        "paths": {
            "/api/v1/resource": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "required": False, "schema": {"type": "integer"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "parameters": [],
                    "requestBody": {"required": False},
                    "responses": {"201": {"description": "Created"}},
                },
            }
        }
    }

    # 1. Removing an endpoint path is breaking
    curr_removed_path = {"paths": {}}
    assert any("Removed endpoint" in v for v in find_breaking_changes(base, curr_removed_path))

    # 2. Removing an HTTP method is breaking
    curr_removed_method = {
        "paths": {
            "/api/v1/resource": {
                "get": base["paths"]["/api/v1/resource"]["get"],
            }
        }
    }
    assert any("Removed HTTP method: POST" in v for v in find_breaking_changes(base, curr_removed_method))

    # 3. Adding a required query parameter is breaking
    curr_added_required = {
        "paths": {
            "/api/v1/resource": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "required": False, "schema": {"type": "integer"}},
                        {"name": "filter", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": base["paths"]["/api/v1/resource"]["post"],
            }
        }
    }
    assert any(
        "Added new required parameter 'filter'" in v
        for v in find_breaking_changes(base, curr_added_required)
    )

    # 4. Mutating parameter type is breaking
    curr_type_changed = {
        "paths": {
            "/api/v1/resource": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "required": False, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": base["paths"]["/api/v1/resource"]["post"],
            }
        }
    }
    assert any("Changed type of parameter 'id'" in v for v in find_breaking_changes(base, curr_type_changed))

    # 5. Removing success response status code is breaking
    curr_status_removed = {
        "paths": {
            "/api/v1/resource": {
                "get": {
                    "parameters": base["paths"]["/api/v1/resource"]["get"]["parameters"],
                    "responses": {"404": {"description": "Not Found"}},
                },
                "post": base["paths"]["/api/v1/resource"]["post"],
            }
        }
    }
    assert any(
        "Removed response status code 200" in v
        for v in find_breaking_changes(base, curr_status_removed)
    )
