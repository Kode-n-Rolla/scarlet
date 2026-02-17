from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SolcAstResult:
    # map: absolute file path -> AST dict (Solidity AST)
    # SCARLET intentionally normalizes keys to absolute paths:
    #   - eliminates ambiguity when different files share the same basename
    #   - makes filtering by "files in scope" deterministic across machines
    ast_by_file: dict[Path, dict[str, Any]]
    errors: list[str]


def _build_standard_json_input(files: list[Path]) -> dict[str, Any]:
    # solc --standard-json is used instead of per-file flags because it:
    #   - returns a single structured JSON response (easy to parse + test)
    #   - supports multi-file compilation in one invocation
    #   - exposes "sources" mapping that can be re-keyed back to file paths
    sources: dict[str, dict[str, str]] = {}
    for f in files:
        # use absolute posix path as key (stable across runs)
        # Important nuance:
        #   Standard JSON "sources" keys are arbitrary strings. Using absolute posix paths
        #   makes the mapping back to real files straightforward and avoids collisions.
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

    # NOTE:
    # This call relies on solc being able to compile the provided sources in isolation.
    # In real Foundry/Hardhat projects this can fail due to remappings/import paths.
    # SCARLET treats that as a reason to fall back to Slither (in cli.py), not as a crash here.
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
        #
        # solc may print warnings / notes / non-JSON diagnostics to stderr even when
        #   stdout is valid JSON. Keeping stderr helps users debug compilation context
        #   (missing imports, wrong solc version, etc.) without losing the AST.
        errors.append(raw_err)

    try:
        out = json.loads(raw_out) if raw_out else {}
    except json.JSONDecodeError:
        # if output is not json, surface both streams
        #
        # This is a hard failure because the caller cannot safely recover any AST.
        # Both streams are included to make bug reports actionable.
        msg = "solc did not return valid JSON."
        if raw_out:
            msg += f"\nstdout:\n{raw_out}"
        if raw_err:
            msg += f"\nstderr:\n{raw_err}"
        return SolcAstResult(ast_by_file={}, errors=[msg])

    # collect structured solc errors, if any
    for e in out.get("errors", []) or []:
        # keep only severe errors for now
        #
        # SCARLET separates "diagnostics" from "hard blockers":
        #   - warnings are useful, but should not force a fallback by themselves
        #   - errors/fatal indicate that parts of AST may be missing or inconsistent
        # The CLI layer decides whether to proceed or fall back based on these.
        sev = e.get("severity")
        fmt = e.get("formattedMessage") or e.get("message") or str(e)
        if sev in {"error", "fatal"}:
            errors.append(fmt)

    ast_by_file: dict[Path, dict[str, Any]] = {}
    sources = out.get("sources", {}) or {}
    for key, v in sources.items():
        ast = v.get("ast")
        if ast:
            # key is whatever was used in "sources" input.
            # Using absolute paths there allows direct Path(key).resolve() mapping here.
            ast_by_file[Path(key).resolve()] = ast

    return SolcAstResult(ast_by_file=ast_by_file, errors=errors)
