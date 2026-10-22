"""Generate frontend/src/contract/generated.ts from the contract JSON Schema.

Single source of truth: core/constellab_core/data/simulation_contract.schema.json.
The output contains the schema itself (as a const, for runtime validation) and one
TypeScript type per ``$defs`` entry. Never edit the generated file by hand.

Run via:   npm run gen:contract            (regenerate)
           npm run gen:contract -- --check (fail if the committed file is stale)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "core" / "constellab_core" / "data" / "simulation_contract.schema.json"
OUTPUT = ROOT / "frontend" / "src" / "contract" / "generated.ts"

PRIMITIVES = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean", "null": "null"}


def ts_type(node: dict[str, Any]) -> str:
    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    kind = node.get("type")
    if kind == "array":
        item = ts_type(node["items"])
        if node.get("minItems") is not None and node.get("minItems") == node.get("maxItems"):
            return "[" + ", ".join([item] * node["minItems"]) + "]"
        return f"{item}[]"
    if kind == "object":
        if "properties" not in node:
            value_ts = ts_type(node.get("additionalProperties", {})) if "additionalProperties" in node else "unknown"
            return f"Record<string, {value_ts}>"
        required = set(node.get("required", []))
        lines = []
        for name, prop in node["properties"].items():
            doc = prop.get("description")
            if doc:
                lines.append(f"  /** {doc} */")
            optional = "" if name in required else "?"
            lines.append(f"  {name}{optional}: {ts_type(prop)};")
        return "{\n" + "\n".join(lines) + "\n}"
    if kind in PRIMITIVES:
        return PRIMITIVES[kind]
    raise SystemExit(f"cannot map schema node to TypeScript: {json.dumps(node)[:80]}")


def render(schema: dict[str, Any]) -> str:
    out = [
        "// GENERATED FILE - do not edit. Source: core/constellab_core/data/simulation_contract.schema.json",
        "// Regenerate with: npm run gen:contract",
        "",
        f"export const SCHEMA_VERSION = {json.dumps(schema['x-schema-version'])};",
        "",
        "/** The contract schema, embedded so the renderer can validate snapshots at runtime. */",
        "export const SIMULATION_CONTRACT_SCHEMA = " + json.dumps(schema, indent=2) + " as const;",
        "",
    ]
    for name, node in schema["$defs"].items():
        doc = node.get("description")
        if doc:
            out.append(f"/** {doc} */")
        body = ts_type(node)
        keyword = "interface" if node.get("type") == "object" else "type"
        out.append(f"export {keyword} {name} {'' if keyword == 'interface' else '= '}{body}{'' if keyword == 'interface' else ';'}")
        out.append("")
    names = " | ".join(f'"{n}"' for n in schema["$defs"])
    out.append(f"export type DefinitionName = {names};")
    out.append("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    content = render(schema)
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; run `npm run gen:contract`", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is up to date")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
