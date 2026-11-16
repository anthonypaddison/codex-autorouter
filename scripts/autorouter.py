#!/usr/bin/env python3
"""Configure the existing plugin without installing it or changing Codex defaults."""

from __future__ import annotations

import argparse
import json
import os
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
    parser.add_argument("--provider", default="openai", choices=("openai",))
    parser.add_argument("--credential-env")
    enabled = parser.add_mutually_exclusive_group()
    enabled.add_argument("--enabled", dest="enabled", action="store_true")
    enabled.add_argument("--disabled", dest="enabled", action="store_false")
    parser.set_defaults(enabled=None)
    parser.add_argument("--allow", action="append", metavar="MODEL=EFFORT[,EFFORT]",
                        help="Permitted pairs, including the current root pair to allow direct execution")
    parser.add_argument("--fallback", metavar="MODEL=EFFORT")
    parser.add_argument("--timeout-seconds", type=float,
                        default=routing_config.DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
                        help="Total classifier deadline in seconds (1–30; default: 10; no retries)")
    args = parser.parse_args(argv)
    path = args.config or routing_config.config_path()
    try:
        if args.command == "status":
            config = routing_config.load_config(path)
            print(json.dumps({"status": "configured" if config else "setup_required", "config": config,
                              "credential_environment_present": bool(config and config['schema_version'] == 2
                                  and config['classifier']['credential_env'] in os.environ),
                              "execution_verified": False,
                              "runtime_routing": ("reconfiguration_required" if config and config['schema_version'] == 1 else
                                                  "disabled" if config and not config['enabled'] else
                                                  "configured_not_runtime_verified" if config else "legacy_compatibility"),
                              "classifier_isolation": "api_tools_disabled",
                              "executor_compatibility": "codex_native_validation"}))
            return 0
        models = available_models()
        if args.command == "models":
            print(json.dumps({"models": models, "executor_models": models,
                              "classifier_provider": "openai", "classifier_models": "user_supplied_api_model_id",
                              "model_access": "catalogue_only_not_inference_verified"}))
            return 0
        if not all((args.classifier, args.classifier_effort, args.credential_env, args.allow, args.fallback)) or args.enabled is None:
            if not sys.stdin.isatty():
                parser.error("setup requires classifier/effort, credential-env, allow, fallback and --enabled/--disabled without a TTY")
            for model, efforts in models.items():
                print(model + ": " + ", ".join(efforts), file=sys.stderr)
            print("API classification uses separate API-account billing. Never enter a key here.", file=sys.stderr)
            args.provider = input("Classifier provider [openai]: ").strip() or "openai"
            args.classifier = input("API classifier model (not the Codex catalogue): ").strip()
            args.classifier_effort = input("API classifier effort: ").strip()
            args.credential_env = input("API credential environment VARIABLE NAME (not its value): ").strip()
            print("Include the current root model and effort to permit direct execution when selected.", file=sys.stderr)
            args.allow = input("Permitted MODEL=EFFORT[,EFFORT] pairs (space separated): ").split()
            args.fallback = input("Fallback MODEL=EFFORT: ").strip()
            timeout = input(f"Classifier timeout in seconds [{args.timeout_seconds:g}]: ").strip()
            if timeout:
                args.timeout_seconds = float(timeout)
            args.enabled = input("Enable separately billed API classification? [y/N]: ").strip().lower() == "y"
        executors = []
        for value in args.allow:
            model, efforts = value.split("=", 1)
            executors.append({"model": model, "efforts": efforts.split(",")})
        model, effort = args.fallback.split("=", 1)
        config = routing_config.validate_config({
            "schema_version": 2, "enabled": args.enabled,
            "classifier": {"provider": args.provider, "model": args.classifier, "effort": args.classifier_effort,
                           "credential_env": args.credential_env},
            "executors": executors, "fallback": {"model": model, "effort": effort}, "timeout_seconds": args.timeout_seconds,
        }, models)
        backup = routing_config.save_config(path, config)
        print(json.dumps({"status": "configured", "path": str(path), "backup": str(backup) if backup else None,
                          "model_access": "catalogue_only_not_inference_verified", "live_classifier_calls": 0,
                          "runtime_routing": "configured_not_runtime_verified" if args.enabled else "disabled",
                          "classifier_isolation": "api_tools_disabled", "executor_compatibility": "codex_native_validation"}))
        return 0
    except (routing_config.ConfigError, ValueError, OSError, EOFError) as exc:
        print("Autorouter setup failed: " + (str(exc) if isinstance(exc, routing_config.ConfigError) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
