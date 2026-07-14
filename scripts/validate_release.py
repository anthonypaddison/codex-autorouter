#!/usr/bin/env python3
"""Self-contained structural and hygiene validation for the plugin archive."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
HOOKS = ROOT / "hooks" / "hooks.json"
SKILL = ROOT / "skills" / "route-gpt-5-6-work"
EVENTS = {"UserPromptSubmit", "SubagentStart", "PostToolUse", "SubagentStop", "Stop"}
AGENTS = {
    "gpt56_luna_worker.toml",
    "gpt56_terra_worker.toml",
    "gpt56_terra_deep.toml",
    "gpt56_sol_owner.toml",
    "gpt56_sol_deep.toml",
    "gpt56_sol_xhigh.toml",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(manifest.get("name") == "gpt-5-6-router", "stable plugin package name changed")
    folder_names = {ROOT.name.lower(), ROOT.parent.name.lower()}
    require(
        bool(folder_names & {"gpt-5-6-router", "codex-autorouter"}),
        "source folder must use the package or public repository name",
    )
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(manifest.get("version")))), "invalid semver")
    require(manifest.get("skills") == "./skills/", "skills path must be plugin-relative")
    require((ROOT / manifest["interface"]["logo"]).is_file(), "logo is missing")
    require((ROOT / "scripts" / "check_hooks.py").is_file(), "hook trust checker is missing")
    require((ROOT / "scripts" / "standalonectl.py").is_file(), "standalone lifecycle helper is missing")
    require((ROOT / "docs" / "PRIVACY.md").is_file(), "privacy documentation is missing")
    require((ROOT / "scripts" / "fuzz_router.py").is_file(), "routing fuzz runner is missing")
    require((ROOT / "benchmarks" / "autorouter_bench.py").is_file(), "capability benchmark is missing")
    require((ROOT / "benchmarks" / "README.md").is_file(), "capability benchmark guide is missing")

    hooks = json.loads(HOOKS.read_text(encoding="utf-8")).get("hooks")
    require(isinstance(hooks, dict) and set(hooks) == EVENTS, "unexpected hook event set")
    for groups in hooks.values():
        require(isinstance(groups, list) and groups, "hook event must contain groups")
        for group in groups:
            for hook in group.get("hooks", []):
                require("${PLUGIN_ROOT}" in hook.get("command", ""), "POSIX hook is not relocatable")
                require("%PLUGIN_ROOT%" in hook.get("commandWindows", ""), "Windows hook is not relocatable")

    actual_agents = {path.name for path in (SKILL / "assets" / "agents").glob("*.toml")}
    require(actual_agents == AGENTS, "custom-agent template set changed unexpectedly")
    for name in actual_agents:
        require(re.fullmatch(r"[a-z0-9_]+\.toml", name) is not None, f"custom-agent name is not spawn-compatible: {name}")
        require(f'name = "{Path(name).stem}"' in (SKILL / "assets" / "agents" / name).read_text(encoding="utf-8"), f"custom-agent file/name mismatch: {name}")
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    require(skill_text.startswith("---\nname: route-gpt-5-6-work\n"), "invalid skill frontmatter")
    require("record a prompt hash" not in skill_text.lower(), "skill privacy contract reintroduced prompt hashing")
    hook_source = (SKILL / "scripts" / "router_hook.py").read_text(encoding="utf-8")
    require(
        re.search(r'["\']decision["\']\s*:\s*["\']block["\']', hook_source) is None,
        "terminal-hook hard block can poison Codex session history",
    )

    forbidden = (re.compile(r"/Users/[A-Za-z0-9._-]+/"), re.compile(r"[A-Za-z]:\\Users\\[^\\]+\\"))
    for path in ROOT.rglob("*"):
        require(not path.is_symlink(), f"release contains symlink: {path.relative_to(ROOT)}")
        if path.is_dir():
            require(path.name != "__pycache__", "release contains __pycache__")
            continue
        require(path.suffix not in {".pyc", ".pyo"}, f"release contains bytecode: {path.name}")
        if path.suffix.lower() in {".md", ".json", ".toml", ".py", ".yaml", ".yml", ".svg"}:
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                require(not pattern.search(text), f"source-machine path in {path.relative_to(ROOT)}")
            require(("[" + "TODO:") not in text, f"placeholder in {path.relative_to(ROOT)}")

    print(f"release validation passed: {ROOT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"release validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
