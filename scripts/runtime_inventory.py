#!/usr/bin/env python3
"""Generate a runtime component inventory from a rendered Docker Compose file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value)
    return [value]


def build_inventory(compose_file: Path) -> dict[str, Any]:
    compose = yaml.safe_load(compose_file.read_text()) or {}
    services = compose.get("services") or {}
    inventory_services: list[dict[str, Any]] = []

    for name, service in sorted(services.items()):
        service = service or {}
        build = service.get("build") or {}
        if isinstance(build, str):
            build = {"context": build}
        environment = service.get("environment") or {}
        if isinstance(environment, list):
            env_keys = sorted(str(item).split("=", 1)[0] for item in environment)
        else:
            env_keys = sorted(str(key) for key in environment)
        ports = [
            str(port.get("published") or port.get("target") or port)
            if isinstance(port, dict)
            else str(port)
            for port in _as_list(service.get("ports"))
        ]
        secrets = [
            str(secret.get("source") or secret)
            if isinstance(secret, dict)
            else str(secret)
            for secret in _as_list(service.get("secrets"))
        ]
        inventory_services.append(
            {
                "name": name,
                "image": service.get("image"),
                "build_context": build.get("context"),
                "build_dockerfile": build.get("dockerfile"),
                "command_configured": bool(service.get("command")),
                "public_ports": ports,
                "secrets": sorted(secrets),
                "environment_keys": env_keys,
            }
        )

    return {
        "source": str(compose_file),
        "service_count": len(inventory_services),
        "services": inventory_services,
    }


def write_markdown(inventory: dict[str, Any], path: Path) -> None:
    lines = [
        "# Runtime Component Inventory",
        "",
        f"Source: `{inventory['source']}`",
        f"Services: {inventory['service_count']}",
        "",
        "| Service | Image | Build | Public ports | Secrets |",
        "| --- | --- | --- | --- | --- |",
    ]
    for service in inventory["services"]:
        build = service.get("build_dockerfile") or service.get("build_context") or ""
        lines.append(
            "| {name} | {image} | {build} | {ports} | {secrets} |".format(
                name=service["name"],
                image=service.get("image") or "",
                build=build,
                ports=", ".join(service.get("public_ports") or []),
                secrets=", ".join(service.get("secrets") or []),
            )
        )
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args(argv)

    inventory = build_inventory(args.compose_file)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    write_markdown(inventory, args.markdown_out)
    print(f"Wrote runtime inventory: {args.json_out}")
    print(f"Wrote runtime inventory: {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
