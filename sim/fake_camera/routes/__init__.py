"""Route registry for fake camera simulator."""

import importlib
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

RouteHandler = Callable[..., Any]
_ROUTES: dict[tuple[str, str, str | None], RouteHandler] = {}


def route(
    method: str,
    path: str,
    soap_action: str | None = None,
) -> Callable[[RouteHandler], RouteHandler]:
    """Register HTTP route handler."""

    def decorator(fn: RouteHandler) -> RouteHandler:
        _ROUTES[(method.upper(), path, soap_action)] = fn
        return fn

    return decorator


def find_route(
    method: str,
    path: str,
    soap_action: str | None = None,
) -> RouteHandler | None:
    """Find route handler by method, path, and optional soap action."""
    # Exact match
    handler = _ROUTES.get((method.upper(), path, soap_action))
    if handler is not None:
        return handler
    # Match without soap_action
    if soap_action is not None:
        handler = _ROUTES.get((method.upper(), path, None))
        if handler is not None:
            return handler
    return None


def load_all_routes() -> None:
    """Automatically import all sibling route modules."""
    package_dir = Path(__file__).parent
    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if not module_name.startswith("_"):
            importlib.import_module(f".{module_name}", package=__name__)


# Auto-load on import
load_all_routes()
