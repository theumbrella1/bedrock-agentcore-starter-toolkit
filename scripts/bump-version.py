#!/usr/bin/env python3
"""Bump version in pyproject.toml."""

import re
import sys


def bump_version(version, bump_type):
    """Bump version based on type."""
    parts = version.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2].split("-")[0])

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif bump_type == "premajor":
        return f"{major + 1}.0.0-beta.1"
    elif bump_type == "preminor":
        return f"{major}.{minor + 1}.0-beta.1"
    elif bump_type == "prepatch":
        return f"{major}.{minor}.{patch + 1}-beta.1"
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")


if __name__ == "__main__":
    bump_type = sys.argv[1] if len(sys.argv) > 1 else "patch"

    with open("pyproject.toml", "r") as f:
        content = f.read()

    current_version = re.search(r'version = "([^"]+)"', content).group(1)
    new_version = bump_version(current_version, bump_type)

    content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content)

    with open("pyproject.toml", "w") as f:
        f.write(content)

    print(f"Version bumped from {current_version} to {new_version}")
