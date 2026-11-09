"""Stable executable entry point for the service and teaching commands."""

from .cli.commands import main

if __name__ == "__main__":
    raise SystemExit(main())
