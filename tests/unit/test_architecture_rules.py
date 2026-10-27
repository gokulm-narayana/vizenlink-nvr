"""Architecture enforcement rules verifying boundary isolation and asyncio purity."""

import ast
from pathlib import Path

FORBIDDEN_CAMERA_IMPORT_PREFIXES = (
    "vizenlink_nvr.db",
    "vizenlink_nvr.services",
    "vizenlink_nvr.cli",
    "vizenlink_nvr.secrets",
)
FORBIDDEN_CLI_IMPORT_PREFIXES = ("vizenlink_nvr.camera",)
ASYNCIO_PRIMITIVES = {"Lock", "Event", "Queue", "Semaphore", "Task", "create_task"}


def check_camera_imports(tree: ast.AST, filename: str) -> list[str]:
    """Verify camera module does not import db, services, cli, or secrets."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_CAMERA_IMPORT_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(f"{prefix}."):
                        errors.append(f"{filename}:{node.lineno} imports forbidden '{alias.name}'")
        elif isinstance(node, ast.ImportFrom) and node.module:
            for prefix in FORBIDDEN_CAMERA_IMPORT_PREFIXES:
                if node.module == prefix or node.module.startswith(f"{prefix}."):
                    errors.append(f"{filename}:{node.lineno} imports from forbidden '{node.module}'")
    return errors


def check_cli_imports(tree: ast.AST, filename: str) -> list[str]:
    """Verify cli module does not import camera."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_CLI_IMPORT_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(f"{prefix}."):
                        errors.append(f"{filename}:{node.lineno} imports forbidden '{alias.name}'")
        elif isinstance(node, ast.ImportFrom) and node.module:
            for prefix in FORBIDDEN_CLI_IMPORT_PREFIXES:
                if node.module == prefix or node.module.startswith(f"{prefix}."):
                    errors.append(f"{filename}:{node.lineno} imports from forbidden '{node.module}'")
    return errors


def check_module_level_asyncio(tree: ast.Module, filename: str) -> list[str]:
    """Verify no module-level asyncio primitives exist in top-level statements."""
    errors: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(class_stmt):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Attribute) and func.attr in ASYNCIO_PRIMITIVES:
                            errors.append(f"{filename}:{node.lineno} class-level asyncio.{func.attr}()")
                        elif isinstance(func, ast.Name) and func.id in ASYNCIO_PRIMITIVES:
                            errors.append(f"{filename}:{node.lineno} class-level {func.id}()")
            continue

        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ASYNCIO_PRIMITIVES:
                    errors.append(f"{filename}:{node.lineno} module-level asyncio.{func.attr}()")
                elif isinstance(func, ast.Name) and func.id in ASYNCIO_PRIMITIVES:
                    errors.append(f"{filename}:{node.lineno} module-level {func.id}()")
    return errors


def test_rule_checker_fails_on_synthetic_violations() -> None:
    """Verify the rule checking functions detect synthetic violations as required."""
    # Synthetic forbidden camera import
    bad_camera_ast = ast.parse("from vizenlink_nvr.db.models import Base\nimport vizenlink_nvr.secrets")
    violations = check_camera_imports(bad_camera_ast, "dummy_cam.py")
    assert len(violations) == 2

    # Synthetic forbidden cli import
    bad_cli_ast = ast.parse("from vizenlink_nvr.camera.http import CameraHttp")
    violations_cli = check_cli_imports(bad_cli_ast, "dummy_cli.py")
    assert len(violations_cli) == 1

    # Synthetic module-level asyncio primitive
    bad_asyncio_ast = ast.parse("import asyncio\nlock = asyncio.Lock()\nq = Queue()")
    violations_async = check_module_level_asyncio(bad_asyncio_ast, "dummy_mod.py")
    assert len(violations_async) >= 1


def test_camera_layer_isolation() -> None:
    """src/vizenlink_nvr/camera must never import db, services, cli, or secrets."""
    camera_dir = Path("src/vizenlink_nvr/camera")
    assert camera_dir.is_dir()

    all_errors: list[str] = []
    for py_file in camera_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        all_errors.extend(check_camera_imports(tree, str(py_file)))

    assert not all_errors, "Camera package isolation violated:\n" + "\n".join(all_errors)


def test_cli_layer_isolation() -> None:
    """src/vizenlink_nvr/cli must never import camera."""
    cli_dir = Path("src/vizenlink_nvr/cli")
    assert cli_dir.is_dir()

    all_errors: list[str] = []
    for py_file in cli_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        all_errors.extend(check_cli_imports(tree, str(py_file)))

    assert not all_errors, "CLI package isolation violated:\n" + "\n".join(all_errors)


def test_no_module_level_asyncio_primitives() -> None:
    """No module under src/vizenlink_nvr may instantiate module-level asyncio primitives."""
    src_dir = Path("src/vizenlink_nvr")
    assert src_dir.is_dir()

    all_errors: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        all_errors.extend(check_module_level_asyncio(tree, str(py_file)))

    assert not all_errors, "Module-level asyncio primitives detected:\n" + "\n".join(all_errors)
