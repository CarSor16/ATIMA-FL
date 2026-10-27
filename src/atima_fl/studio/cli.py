"""ATIMA Studio command entry point; no training stack imported at startup."""

import sys

from atima_fl.cli import main as shared_main

STUDIO_COMMANDS = frozenset({
    "ui", "catalog", "datasets", "validate", "plan", "defense-study"
})


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in STUDIO_COMMANDS:
        raise SystemExit(
            "ATIMA Studio commands: ui, catalog, datasets, validate, plan, defense-study"
        )
    return shared_main(args)


if __name__ == "__main__":
    main()
