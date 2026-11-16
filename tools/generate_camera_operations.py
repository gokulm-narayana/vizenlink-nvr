"""Build the packaged LAN operation catalog from the pinned camera OpenAPI document."""

import copy
import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts/camera_api/design/Camera-REST-API.openapi.yaml"
OUTPUT = ROOT / "src/vizenlink_nvr/camera/nuraeye/operation_catalog.json"


class Loader(yaml.SafeLoader):
    """Use JSON booleans: the camera's string 'Off' must never become False."""


Loader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for key, values in Loader.yaml_implicit_resolvers.items():
    Loader.yaml_implicit_resolvers[key] = [v for v in values if v[0] != "tag:yaml.org,2002:bool"]
Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))


def build() -> dict:
    doc = yaml.load(SOURCE.read_text(), Loader=Loader)  # noqa: S506 - subclass of SafeLoader
    operations = {}
    for path, methods in doc["paths"].items():
        for method, definition in methods.items():
            if method not in ("get", "post"):
                continue
            operation = definition["operationId"]
            schema = (
                definition.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            )
            query = {p["name"]: p["schema"] for p in definition.get("parameters", []) if p["in"] == "query"}
            operations[operation] = {
                "method": method.upper(),
                "path": path,
                "schema": schema or {"type": "object", "properties": {}},
                "query": query,
            }
    return {
        "source": "camera_api 6b78d89a (2026-11-04)",
        "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "operations": operations,
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"Generated {len(build()['operations'])} pinned camera operations")
