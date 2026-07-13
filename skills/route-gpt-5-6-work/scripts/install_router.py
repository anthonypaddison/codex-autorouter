#!/usr/bin/env python3
"""Compatibility entrypoint for pre-plugin installations.

This command no longer edits hooks.json. Codex owns plugin hooks. New scripts
should call routerctl.py directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    routerctl = Path(__file__).with_name("routerctl.py")
    arguments = sys.argv[1:]
    if not arguments:
        command = ["status"]
    elif arguments == ["--install"]:
        command = ["activate"]
    elif arguments == ["--uninstall"]:
        command = ["deactivate"]
    else:
        print("usage: install_router.py [--install|--uninstall]", file=sys.stderr)
        return 2
    print(
        "Compatibility mode: plugin hooks are managed by Codex; this command only manages custom agents.",
        file=sys.stderr,
    )
    return subprocess.call([sys.executable, str(routerctl), *command])


if __name__ == "__main__":
    raise SystemExit(main())
