"""Command-line helpers for the Codex runtime package.

``python -m codex_cli_bin download`` fetches the runtime now (useful while
building a Docker image) and prints the path of the ``codex`` executable.
"""

import sys

from . import bundled_codex_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "download"
    if command not in {"download", "path"}:
        print("usage: python -m codex_cli_bin [download|path]", file=sys.stderr)
        return 2
    print(bundled_codex_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
