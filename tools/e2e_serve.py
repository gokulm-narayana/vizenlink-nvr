"""E2E test server launcher.

Serves the built SPA on loopback with a fresh runtime data directory.
Refuses any data directory that does not contain '.e2e' as a safety measure.
"""

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

import uvicorn

from vizenlink_nvr.api.app import create_app
from vizenlink_nvr.config import load_settings
from vizenlink_nvr.services.runtime import open_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run E2E NVR test server")
    parser.add_argument("--port", type=int, required=True, help="Port to listen on (loopback only)")
    parser.add_argument("--data-dir", type=str, required=True, help="Runtime data directory")
    return parser.parse_args()


async def run_server(port: int, data_dir: Path) -> None:
    settings = load_settings(data_dir=data_dir)
    async with open_runtime(settings) as rt:
        if rt.vault is None:
            sys.stderr.write("Fatal: runtime.vault is None\n")
            sys.exit(3)

        app = create_app(session_factory=rt.sessions, runtime=rt)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()


def main() -> None:
    args = parse_args()
    resolved_dir = Path(args.data_dir).resolve()

    if ".e2e" not in resolved_dir.parts:
        sys.stderr.write(f"Safety violation: '{resolved_dir}' must contain a '.e2e' component\n")
        sys.exit(2)

    if resolved_dir.exists():
        shutil.rmtree(resolved_dir)

    resolved_dir.mkdir(parents=True, exist_ok=True)
    (resolved_dir / "recordings").mkdir(parents=True, exist_ok=True)

    if "NVR_SECRETS_BACKEND" not in os.environ:
        os.environ["NVR_SECRETS_BACKEND"] = "file"

    try:
        asyncio.run(run_server(args.port, resolved_dir))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()