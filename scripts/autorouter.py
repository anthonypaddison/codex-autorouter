#!/usr/bin/env python3
"""Configure the existing plugin without installing it or changing Codex defaults."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/route-gpt-5-6-work/scripts"))
import routing_config
import model_catalogue


def available_models() -> dict[str, list[str]]:
    result = model_catalogue.discover_catalogue()
    if result.state != model_catalogue.CatalogueState.COMPLETE:
        return {}
    return {model.canonical_id: list(model.efforts) for model in result.models
            if model.visibility == "list" and model.efforts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "status", "models"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--classifier")
    parser.add_argument("--classifier-effort")
    parser.add_argument("--allow", action="append", metavar="MODEL=EFFORT[,EFFORT]")
    parser.add_argument("--fallback", metavar="MODEL=EFFORT")
    args = parser.parse_args(argv)
    path = args.config or routing_config.config_path()
    try:
        if args.command == "status":
            config = routing_config.load_config(path)
            print(json.dumps({"status": "configured" if config else "setup_required", "config": config,
                              "execution_verified": False, "runtime_routing": "blocked" if config else "legacy_compatibility",
                              "classifier_isolation": "unverified", "executor_compatibility": "unverified"}))
            return 0
        models = available_models()
        if not models:
            raise routing_config.ConfigError("no_fresh_selectable_model_catalogue; open Codex to refresh it")
        if args.command == "models":
            print(json.dumps({"models": models, "model_access": "catalogue_only_not_inference_verified"}))
            return 0
        if not all((args.classifier, args.classifier_effort, args.allow, args.fallback)):
            if not sys.stdin.isatty():
                parser.error("setup requires --classifier, --classifier-effort, --allow and --fallback without a TTY")
            for model, efforts in models.items():
                print(model + ": " + ", ".join(efforts), file=sys.stderr)
            args.classifier = input("Classifier model: ").strip()
            args.classifier_effort = input("Classifier effort: ").strip()
            args.allow = input("Permitted MODEL=EFFORT[,EFFORT] pairs (space separated): ").split()
            args.fallback = input("Fallback MODEL=EFFORT: ").strip()
        executors = []
        for value in args.allow:
            model, efforts = value.split("=", 1)
            executors.append({"model": model, "efforts": efforts.split(",")})
        model, effort = args.fallback.split("=", 1)
        config = routing_config.validate_config({
            "schema_version": 1, "classifier": {"model": args.classifier, "effort": args.classifier_effort},
            "executors": executors, "fallback": {"model": model, "effort": effort}, "timeout_seconds": 6,
        }, models)
        backup = routing_config.save_config(path, config)
        print(json.dumps({"status": "configured", "path": str(path), "backup": str(backup) if backup else None,
                          "model_access": "catalogue_only_not_inference_verified", "live_classifier_calls": 0,
                          "runtime_routing": "blocked", "classifier_isolation": "unverified",
                          "executor_compatibility": "unverified"}))
        return 0
    except (routing_config.ConfigError, ValueError, OSError, EOFError) as exc:
        print("Autorouter setup failed: " + (str(exc) if isinstance(exc, routing_config.ConfigError) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
