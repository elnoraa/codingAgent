"""CI/CD integration for detecting and checking pipeline status."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from src.tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

# CI provider detection: config files
CI_DETECTORS: dict[str, dict[str, Any]] = {
    "github_actions": {
        "config_files": [".github/workflows/"],
        "config_file_pattern": ".github/workflows/*.yml",
        "validate_cmd": None,  # No built-in validation; YAML parse only
    },
    "gitlab_ci": {
        "config_files": [".gitlab-ci.yml"],
        "validate_cmd": None,
    },
    "circleci": {
        "config_files": [".circleci/config.yml"],
        "validate_cmd": ["circleci", "config", "validate"],
    },
    "jenkins": {
        "config_files": ["Jenkinsfile"],
        "validate_cmd": None,
    },
    "travis": {
        "config_files": [".travis.yml"],
        "validate_cmd": ["travis", "lint"],
    },
}


def detect_ci_provider(working_dir: str) -> str | None:
    """Detect which CI/CD provider is configured in the project."""
    for provider, config in CI_DETECTORS.items():
        for cfg in config["config_files"]:
            path = os.path.join(working_dir, cfg)
            if os.path.exists(path):
                return provider
    return None


def validate_ci_config(working_dir: str, provider: str | None = None) -> str:
    """Validate CI configuration file syntax."""
    if provider is None:
        provider = detect_ci_provider(working_dir)

    if provider is None:
        return "No CI configuration detected."

    detector = CI_DETECTORS.get(provider, {})
    validate_cmd = detector.get("validate_cmd")

    if validate_cmd is None:
        # Do a basic YAML parse check
        config_files = detector.get("config_files", [])
        for cfg in config_files:
            path = os.path.join(working_dir, cfg)
            if os.path.exists(path):
                try:
                    import yaml
                    with open(path) as f:
                        yaml.safe_load(f)
                    return f"{provider}: config is valid YAML"
                except Exception as e:
                    return f"{provider}: YAML error: {e}"
        return f"{provider}: config file not found"

    try:
        result = subprocess.run(
            validate_cmd,
            capture_output=True, text=True, cwd=working_dir,
            timeout=30,
        )
        if result.returncode == 0:
            return f"{provider}: config is valid"
        return f"{provider}: validation failed:\n{result.stderr or result.stdout}"
    except FileNotFoundError:
        return f"{provider}: CLI tool not found. Install the {provider} CLI."
    except Exception as e:
        return f"{provider}: validation error: {e}"


def check_pipeline_status(working_dir: str) -> str:
    """Check latest pipeline status using gh CLI (GitHub Actions)."""
    try:
        # Check if gh is installed and authenticated
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return "GitHub CLI (gh) not authenticated. Run 'gh auth login' first."

        # Get latest workflow runs
        result = subprocess.run(
            ["gh", "run", "list", "--limit", "10"],
            capture_output=True, text=True, cwd=working_dir,
            timeout=30,
        )
        if result.returncode == 0:
            return f"Latest workflow runs:\n{result.stdout}"
        return f"Error fetching runs: {result.stderr}"

    except FileNotFoundError:
        return "GitHub CLI (gh) not installed."
    except Exception as e:
        return f"Error: {e}"


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    action = args.get("action", "detect").lower()
    logger.info("execute: action=%s, provider=%s", action, args.get("provider"))

    if action == "detect":
        provider = detect_ci_provider(ctx.working_directory)
        if provider:
            logger.info("Detected CI provider: %s", provider)
            return f"Detected CI provider: {provider}"
        logger.info("No CI/CD configuration detected in %s", ctx.working_directory)
        return "No CI/CD configuration detected."

    elif action == "validate":
        provider = args.get("provider") or None
        result = validate_ci_config(ctx.working_directory, provider)
        logger.info("CI validation result: %s", result[:100])
        return result

    elif action == "status":
        logger.info("Checking pipeline status in %s", ctx.working_directory)
        return check_pipeline_status(ctx.working_directory)

    elif action == "providers" or action == "list":
        result = ["\n  Supported CI Providers:"]
        result.append("  " + "─" * 40)
        for provider, config in CI_DETECTORS.items():
            config_files = ", ".join(config["config_files"])
            result.append(f"  {provider:<20} ({config_files})")
        return "\n".join(result)

    else:
        logger.warning("Unknown CI action: %s", action)
        return (
            f"Unknown action: {action}\n"
            f"Available actions: detect, validate, status, providers"
        )


ci_tool = Tool(
    name="ci",
    description=(
        "CI/CD integration. Actions: detect (detect CI provider from project files), "
        "validate (validate CI config syntax), status (check latest pipeline status via gh CLI), "
        "providers (list supported CI providers)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["detect", "validate", "status", "providers"],
            },
            "provider": {
                "type": "string",
                "description": "Specific provider to validate (optional, auto-detects if omitted)",
            },
        },
        "required": ["action"],
    },
    execute=execute,
    read_only=False,
)
