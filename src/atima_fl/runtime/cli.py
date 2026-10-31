"""ATIMA Runtime command entry point; load Flower only for execution."""

import sys

from atima_fl.cli import main as shared_main

RUNTIME_COMMANDS = frozenset({
    "run", "launch", "analyze", "compare-defenses",
    "statistics", "defense-statistics", "prepare-dirichlet"
})


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in RUNTIME_COMMANDS:
        raise SystemExit(
            "ATIMA Runtime commands: run, launch, analyze, compare-defenses, "
            "statistics, defense-statistics, prepare-dirichlet"
        )
    return shared_main(args)


if __name__ == "__main__":
    main()
