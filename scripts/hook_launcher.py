#!/usr/bin/env python3
"""Run only the router hook shipped below the selected plugin root."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path


HOOK_RELATIVE_PATH = Path("skills/route-gpt-5-6-work/scripts/router_hook.py")
MISSING_MARKER = ".autorouter-missing-exact-hook-v1"


def _claim_first_diagnostic(data_root: Path) -> bool:
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(data_root / MISSING_MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    except OSError:
        # Failing open is more important than making diagnostics stateful when
        # the host-provided data directory itself is unavailable.
        return True
    os.close(descriptor)
    return True


def launch(plugin_root: Path, data_root: Path) -> int:
    resolved_root = plugin_root.resolve()
    target = (resolved_root / HOOK_RELATIVE_PATH).resolve()
    if target.is_relative_to(resolved_root) and target.is_file():
        original_argv = sys.argv
        try:
            sys.argv = [str(target)]
            runpy.run_path(str(target), run_name="__main__")
        finally:
            sys.argv = original_argv
        return 0

    payload: dict[str, object] = {"continue": True}
    if _claim_first_diagnostic(data_root):
        payload["systemMessage"] = (
            "Autorouter readiness DEGRADED: the selected plugin root does not contain its router hook. "
            "Routing failed open; reinstall this exact plugin build and open a fresh task."
        )
    print(json.dumps(payload, separators=(",", ":")))
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"continue": True, "systemMessage": "Autorouter readiness DEGRADED: hook launcher received no exact plugin root."}, separators=(",", ":")))
        return 0
    plugin_root = Path(sys.argv[1])
    data_value = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    data_root = Path(data_value) if data_value else plugin_root / ".autorouter-data"
    return launch(plugin_root, data_root)


if __name__ == "__main__":
    raise SystemExit(main())
