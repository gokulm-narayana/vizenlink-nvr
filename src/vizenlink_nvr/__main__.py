"""Allow `python -m vizenlink_nvr ...` (used by the MediaMTX segment hook)."""

from vizenlink_nvr.cli.app import app

if __name__ == "__main__":
    app()
