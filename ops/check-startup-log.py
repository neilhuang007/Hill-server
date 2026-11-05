#!/usr/bin/env python3
"""Reject startup errors while recognizing one preserved map's legacy optional attributes."""
import re
import sys
from pathlib import Path

PROBLEMS = re.compile(r"Failed to load datapack|Could not load datapack|Failed to parse|Couldn.t parse|registry.*error|Unknown registry|Missing required feature|watchdog|Exception|ERROR", re.IGNORECASE)
LEGACY_HEADER = re.compile(r'^\[[^\]]+\] \[Server thread/WARN\]: \[net\.minecraft\.world\.entity\.EntityType\] Serialization errors:$')
REGISTRY_KEY = re.compile(r'Unknown registry key in ResourceKey\[minecraft:root / minecraft:attribute\]: ([a-z0-9_:]+)')
LEGACY_ATTRIBUTES = {'forge:entity_gravity', 'forge:step_height_addition'}


def inspect(text):
    lines = text.splitlines()
    failures = []
    legacy_count = 0
    index = 0
    while index < len(lines):
        if LEGACY_HEADER.fullmatch(lines[index]) and index + 1 < len(lines):
            detail = lines[index + 1]
            keys = REGISTRY_KEY.findall(detail)
            # Match the warning envelope, attribute field and every error clause.
            # A new attribute, a different registry, or an ERROR level still fails.
            if detail.startswith(": Failed to decode value '") and "from field 'attributes': " in detail and keys and set(keys) <= LEGACY_ATTRIBUTES:
                errors = detail.split("from field 'attributes': ", 1)[1].split('; ')
                if all(REGISTRY_KEY.fullmatch(error) for error in errors):
                    legacy_count += 1
                    index += 2
                    continue
        if PROBLEMS.search(lines[index]):
            failures.append((index + 1, lines[index]))
        index += 1
    return failures, legacy_count


if __name__ == '__main__':
    failures, legacy_count = inspect(Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace'))
    if legacy_count:
        print(f'Known legacy map attribute warnings: {legacy_count}. Optional Forge gravity and step height attributes are unavailable on vanilla Paper.')
    for number, line in failures:
        print(f'{number}:{line}', file=sys.stderr)
    raise SystemExit(1 if failures else 0)
