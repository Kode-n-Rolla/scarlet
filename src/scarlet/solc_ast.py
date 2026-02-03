from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SolcAstResult:
    # map: absolute file path -> AST dict (Solidity AST)
    ast_by_file: dict[Path, dict[str, Any]]
    errors: list[str]


def _build_standard_json_input(files: list[Path]) -> dict[str, Any]:
    sources: dict[str, dict[str, str]] = {}
    for f in files:
        # use absolute posix path as key (stable across runs)
        key = f.resolve().as_posix()
        sources[key] = {"content": f.read_text(encoding="utf-8")}

    return {
        "language": "Solidity",
        "sources": sources,
        "settings": {
            "outputSelection": {
                "*": {
                    "": ["ast"]
                }
            }
        },
    }


def parse_ast(files: list[Path], solc_bin: str = "solc") -> SolcAstResult:
    if not files:
        return SolcAstResult(ast_by_file={}, errors=[])

    inp = _build_standard_json_input(files)
    proc = subprocess.run(
        [solc_bin, "--standard-json"],
        input=json.dumps(inp).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    # solc sometimes prints non-json to stderr; we keep it if needed
    raw_out = proc.stdout.decode("utf-8", errors="replace").strip()
    raw_err = proc.stderr.decode("utf-8", errors="replace").strip()

    errors: list[str] = []
    if raw_err:
        # keep as a diagnostic, but not necessarily a failure
        errors.append(raw_err)

    try:
        out = json.loads(raw_out) if raw_out else {}
    except json.JSONDecodeError:
        # if output is not json, surface both streams
        msg = "solc did not return valid JSON."
        if raw_out:
            msg += f"\nstdout:\n{raw_out}"
        if raw_err:
            msg += f"\nstderr:\n{raw_err}"
        return SolcAstResult(ast_by_file={}, errors=[msg])

    # collect structured solc errors, if any
    for e in out.get("errors", []) or []:
        # keep only severe errors for now
        sev = e.get("severity")
        fmt = e.get("formattedMessage") or e.get("message") or str(e)
        if sev in {"error", "fatal"}:
            errors.append(fmt)

    ast_by_file: dict[Path, dict[str, Any]] = {}
    sources = out.get("sources", {}) or {}
    for key, v in sources.items():
        ast = v.get("ast")
        if ast:
            ast_by_file[Path(key).resolve()] = ast

    return SolcAstResult(ast_by_file=ast_by_file, errors=errors)
