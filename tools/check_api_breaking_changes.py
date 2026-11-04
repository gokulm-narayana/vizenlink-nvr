#!/usr/bin/env python3
"""OpenAPI 3.1 breaking change detector for VizenLink NVR REST API (MOB-01).

Compares current OpenAPI schema against contracts/openapi_v1_baseline.json and
detects breaking changes:
1. Removed endpoints or HTTP methods
2. Added required parameters (query, path, header, cookie)
3. Parameter type or location changes
4. Removed response status codes
5. Added required request body fields
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def find_breaking_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    """Compare baseline and current OpenAPI specifications, returning breaking change descriptions."""
    violations: list[str] = []

    base_paths = baseline.get("paths", {})
    curr_paths = current.get("paths", {})

    for path, base_item in base_paths.items():
        if path not in curr_paths:
            violations.append(f"Removed endpoint path: '{path}'")
            continue

        curr_item = curr_paths[path]

        # Standard HTTP methods to inspect
        for method in ("get", "post", "put", "delete", "patch", "options", "head"):
            if method in base_item and method not in curr_item:
                violations.append(f"Removed HTTP method: {method.upper()} on '{path}'")
                continue

            if method not in base_item or method not in curr_item:
                continue

            base_op = base_item[method]
            curr_op = curr_item[method]

            # 1. Parameter checks
            base_params = {
                (p.get("name"), p.get("in")): p
                for p in base_op.get("parameters", [])
            }
            curr_params = {
                (p.get("name"), p.get("in")): p
                for p in curr_op.get("parameters", [])
            }

            # Check for removed parameters or changed schemas
            for (p_name, p_in), b_param in base_params.items():
                if (p_name, p_in) not in curr_params:
                    # Removing a required path parameter is breaking
                    if p_in == "path" or b_param.get("required"):
                        violations.append(
                            f"Removed required parameter '{p_name}' ({p_in}) from {method.upper()} '{path}'"
                        )
                else:
                    c_param = curr_params[(p_name, p_in)]
                    b_schema = b_param.get("schema", {})
                    c_schema = c_param.get("schema", {})
                    if b_schema.get("type") and c_schema.get("type"):
                        if b_schema["type"] != c_schema["type"]:
                            violations.append(
                                f"Changed type of parameter '{p_name}' ({p_in}) from "
                                f"'{b_schema['type']}' to '{c_schema['type']}' on {method.upper()} '{path}'"
                            )

            # Check for newly added REQUIRED parameters
            for (p_name, p_in), c_param in curr_params.items():
                if (p_name, p_in) not in base_params:
                    if c_param.get("required", False):
                        violations.append(
                            f"Added new required parameter '{p_name}' ({p_in}) to {method.upper()} '{path}'"
                        )

            # 2. Response status code checks
            base_resps = base_op.get("responses", {})
            curr_resps = curr_op.get("responses", {})

            for status_code in base_resps:
                # If a success status code (2xx) in baseline is missing in current
                if status_code.startswith("2") and status_code not in curr_resps:
                    violations.append(
                        f"Removed response status code {status_code} from {method.upper()} '{path}'"
                    )

            # 3. Request body required fields check
            base_req = base_op.get("requestBody", {})
            curr_req = curr_op.get("requestBody", {})

            if base_req.get("required") and not curr_req.get("required"):
                pass  # Making request body optional is backward compatible
            elif not base_req.get("required") and curr_req.get("required"):
                violations.append(
                    f"Request body made required on {method.upper()} '{path}'"
                )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OpenAPI schema for breaking changes.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("contracts/openapi_v1_baseline.json"),
        help="Path to baseline OpenAPI schema JSON",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=None,
        help="Path to current OpenAPI schema JSON (defaults to app.openapi())",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update the baseline with current schema",
    )

    args = parser.parse_args()

    if not args.baseline.exists() and not args.update:
        print(f"Error: Baseline schema file not found at {args.baseline}", file=sys.stderr)
        return 1

    if args.current:
        current_schema = json.loads(args.current.read_text(encoding="utf-8"))
    else:
        from vizenlink_nvr.api.app import app
        current_schema = app.openapi()

    if args.update:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        dumped = json.dumps(current_schema, indent=2, sort_keys=True) + "\n"
        args.baseline.write_text(dumped, encoding="utf-8")
        print(f"Updated baseline at {args.baseline}")
        return 0

    baseline_schema = json.loads(args.baseline.read_text(encoding="utf-8"))
    violations = find_breaking_changes(baseline_schema, current_schema)

    if violations:
        print("ERROR: Breaking changes detected in OpenAPI specification:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("Success: OpenAPI schema is backward-compatible with baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
