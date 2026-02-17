from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json

import os
os.environ["RICH_TRACEBACK"] = "0"

#
# NOTE:
# Typer uses Rich for tracebacks by default; in CLI tools this can be too noisy and can
#   accidentally swallow/pretty-print errors in a way that hides the real root-cause
#   (especially when piping output or when users copy logs into issues).
# Explicitly disable Rich tracebacks to keep stderr deterministic and easier to debug.

import sys
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

import typer

from .slither_index import build_index_with_slither
from .indexer import FunctionInfo, EntrypointInfo, SinkInfo

from .scope import resolve_scope, subtract_out_of_scope
from .solc_ast import parse_ast
from .indexer import build_index, to_dict
from .report.md import render_index_md_from_dict, render_entrypoints_md_from_dict, render_sinks_md_from_dict #,render_index_md
from .analyzers.entrypoints import collect_entrypoints
from .analyzers.sinks import collect_sinks


app = typer.Typer(
    no_args_is_help=True,
    add_help_option=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
)

class Spinner:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._msg = ""
        self._lock = threading.Lock()
        self._frames = ["|", "/", "-", "\\"]

    def update(self, msg: str) -> None:
        with self._lock:
            self._msg = msg

    def start(self, initial: str = "") -> None:
        if not self.enabled:
            return
        self.update(initial)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        # clear line
        sys.stderr.write("\r" + " " * 120 + "\r")
        sys.stderr.flush()

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._frames[i % len(self._frames)]
            with self._lock:
                msg = self._msg
            sys.stderr.write(f"\r{frame} {msg}")
            sys.stderr.flush()
            time.sleep(0.08)
            i += 1


def _write_output(content: str, out: Optional[Path]) -> None:
    # Single output gateway:
    #   - stdout when no --out is provided (easy piping)
    #   - file write when --out is set (CI-friendly artifacts)
    # Keeping this logic centralized prevents subtle differences between modes
    #   (e.g., missing trailing newline, encoding issues, or broken parent dirs).  
    if out is None:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")

def _looks_like_script(path: str) -> bool:
    # Used as a conservative heuristic when deciding how to treat user-provided scope
    #   inputs. SCARLET only check the shebang header to avoid reading/parsing entire files
    #   and to keep the CLI fast on large repos.
    try:
        p = Path(path)
        if not p.exists():
            return False
        head = p.read_bytes()[:2]
        return head == b"#!"
    except Exception:
        return False

def _find_foundry_root(start: Path) -> Path:
    # Slither behaves best when invoked from a project root (foundry/hardhat),
    #   because it can resolve remappings/libs properly. When the scope is a .txt list
    #   or a nested file, SCARLET walk upwards to find foundry.toml and use that as entry.
    cur = start if start.is_dir() else start.parent
    while True:
        if (cur / "foundry.toml").exists():
            return cur
        if cur.parent == cur:
            return start if start.is_dir() else start.parent
        cur = cur.parent

def _filter_contracts_for_output(
    contracts: list[dict],
    include_libraries: bool,
    include_interfaces: bool,
) -> list[dict]:
    # Output filtering is intentionally *presentation-only*.
    # SCARLET still parse/build the full internal index first, but avoid showing
    #   interface/library entries by default to keep reports focused on "deployable"
    #   units. This prevents user confusion (interfaces often contain many signatures
    #   that are not implemented here, libraries can inflate reports with helpers).
    #
    # IMPORTANT: analyzers may still need to see libs/interfaces internally, so
    #   filtering happens at the final payload stage.
    allowed = {"contract"}
    if include_libraries:
        allowed.add("library")
    if include_interfaces:
        allowed.add("interface")

    out: list[dict] = []
    for c in contracts:
        kind = (c.get("kind") or "contract").lower()
        if kind in allowed:
            out.append(c)
    return out

def _filter_entrypoints_for_output(entrypoints, include_libraries: bool, include_interfaces: bool):
    out = []
    for ep in entrypoints:
        kind = (ep.get("contract_kind") or "").lower()
        if kind == "library" and not include_libraries:
            continue
        if kind == "interface" and not include_interfaces:
            continue
        out.append(ep)
    return out

@app.command()
def index(
    scope: str = typer.Option(..., "--scope", help="Scope: .sol file, directory, or .txt list of paths"),
    out_of_scope: Optional[str] = typer.Option(None, "--out-of-scope", "-oos", help="Exclude: .sol, directory, or .txt list"),
    entrypoints: bool = typer.Option(
        False,
        "--entrypoints", "-ep",
        help="Craft entrypoints map (public/external + receive/fallback) in the report",
    ),
    sinks: bool = typer.Option(
        False,
        "--sinks", "-sinks",
        help="Craft sinks map (external influence points: calls-out, balanceOf, etc.)",
    ),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write output to file (.md or .json) instead of stdout"),
    solc: str = typer.Option(
        os.getenv("SCARLET_SOLC", "solc"),
        "--solc",
        help="Solc binary name/path (can be set via SCARLET_SOLC)",
    ),
    no_progress: bool = typer.Option(False, "--no-progress", help="Disable spinner/progress output"),
    full: bool = typer.Option(
        False,
        "--full",
        help="Include internal/private functions",
    ),
    include_libraries: bool = typer.Option(
        False,
        "--include-libraries",
        help="Include libraries in the report",
    ),
    include_interfaces: bool = typer.Option(
        False,
        "--include-interfaces",
        help="Include interfaces in the report",
    ),
) -> None:
    # Output format is determined by --out extension.
    # If --out is omitted, default to markdown in stdout.
    #
    # CLI contract:
    #   - stdout defaults to Markdown for human reading / quick copy-paste
    #   - explicit --out chooses the format based on extension (md/json)
    # This avoids a separate --format flag and makes shell usage predictable.
    if out is None:
        fmt = "md"
    else:
        ext = out.suffix.lower()
        if ext == ".md":
            fmt = "md"
        elif ext == ".json":
            fmt = "json"
        else:
            raise typer.BadParameter("out file must end with .md or .json (e.g. report.md or report.json)")

    if entrypoints and sinks:
        raise typer.BadParameter("Use either --entrypoints or --sinks (not both) for now.")

    included = resolve_scope(scope)
    # scope_dir is used as the logical "project directory" in reports.
    # If user points to a file, SCARLET anchor to its parent so relative paths
    # in markdown/json remain stable and not tied to a single file path.
    scope_dir = Path(scope).expanduser().resolve()
    if scope_dir.is_file():
        scope_dir = scope_dir.parent

    scoped = subtract_out_of_scope(included, out_of_scope)
    files = scoped.final

    # --- Foundry default excludes (no need to pass -oos every time) ---
    if out_of_scope is None:
        # Ergonomics: Foundry repos typically include lib/, script/, test/ which are
        #   (a) dependencies, (b) deployment scripts, or (c) tests. Including them
        #   by default makes reports noisy and slows down parsing.
        #
        # Users can still opt-in by explicitly providing --out-of-scope to override
        #   this behavior, but "no flags" should behave like "audit src/".
        project_root = Path(scope).expanduser().resolve()
        if project_root.is_dir() and (project_root / "foundry.toml").exists():
            lib_dir = project_root / "lib"
            script_dir = project_root / "script"
            test_dir = project_root / "test"
            files = [
                p for p in files
                if not p.is_relative_to(lib_dir) and not p.is_relative_to(script_dir) and not p.is_relative_to(test_dir)
            ]


    if not files:
        _write_output("No .sol files in scope (after out-of-scope filtering).", out)
        raise typer.Exit(code=0)

    # --- Attempt 1: solc AST path ---
    spinner = Spinner(enabled=not no_progress)
    spinner.start(f"Parsing with solc... Progress {len(files)} file(s)")
    
    # Strategy:
    #   Prefer solc AST parsing because it gives the richest, version-accurate view
    #   of the code (needed for sinks and more precise analysis). Slither fallback
    #   is best-effort and may miss details when compilation context is incomplete.

    # Resolve 'solc' to an actual path for diagnostics
    resolved_solc = shutil.which(solc) if solc == "solc" else solc

    ast_res = parse_ast(files, solc_bin=solc)
    spinner.stop()

    fatal_errors = [e for e in ast_res.errors if "error" in e.lower() or "fatal" in e.lower() or "compiler error" in e.lower()]
    # SCARLET only treat truly fatal compiler output as a hard stop.
    # Non-fatal warnings (or partial failures in multi-file repos) shouldn't
    #   force a fallback, because Slither can be *less* accurate and also fail
    #   differently. This heuristic is intentionally conservative.

    if fatal_errors:
        sys.stderr.write("Solc errors:\n" + "\n".join(ast_res.errors) + "\n")
        sys.stderr.flush()


    if not fatal_errors:
        report = build_index(scope_dir=scope_dir, files=files, ast_res=ast_res, entrypoints=entrypoints, sinks=sinks)
        payload = to_dict(report)
        # At this point payload is the single source of truth for rendering.
        # All "modes" (index/entrypoints/sinks) are simply projections of the same
        #   internal model, so output differences stay consistent and testable.

        if entrypoints:
            # ENTRYPOINTS MODE (contracts only; no interfaces/libs by default)
            eps = payload.get("entrypoints", []) or []
            eps = [ep for ep in eps if (ep.get("contract_kind") or "").lower() == "contract"]

            payload = {
                "directory": payload.get("directory"),
                "files": payload.get("files", []),
                "entrypoints": eps,
            }
            # SCARLET intentionally return a reduced payload in ep/sinks modes.
            # It keeps JSON stable for downstream tooling and keeps Markdown focused
            #   on what the user asked for (no extra sections that look like "missing").

            if fmt == "json":
                text = json.dumps(payload, indent=2, ensure_ascii=False)
            else:
                text = render_entrypoints_md_from_dict(payload)

        elif sinks:
            # SINKS MODE
            sks = payload.get("sinks", []) or []
            sks = [s for s in sks if (s.get("contract_kind") or "").lower() == "contract"]

            payload = {
                "directory": payload.get("directory"),
                "files": payload.get("files", []),
                "sinks": sks,
            }
            # Same reduced-payload rationale as entrypoints mode:
            #   consumers can treat the output as "one primary section" without
            #   guessing which other keys might appear.

            if fmt == "json":
                text = json.dumps(payload, indent=2, ensure_ascii=False)
            else:
                text = render_sinks_md_from_dict(payload)

        else:
            # INDEX MODE
            payload["contracts"] = _filter_contracts_for_output(
                payload.get("contracts", []),
                include_libraries=include_libraries,
                include_interfaces=include_interfaces,
            )
            payload.pop("entrypoints", None)
            payload.pop("sinks", None)

            if fmt == "json":
                text = json.dumps(payload, indent=2, ensure_ascii=False)
            else:
                text = render_index_md_from_dict(payload)

        _write_output(text, out)
        raise typer.Exit(code=0)


    # --- Fallback: Slither path ---
    # If solc failed (e.g. 403 via solc-select), use Slither to build index.
    sys.stderr.write("Solc failed; falling back to Slither indexer.\n")

    # This fallback exists for real-world ergonomics: many users have broken solc
    #   environments (solc-select, missing versions, CI images, etc.). Slither can
    #   still recover a useful *index* even if full compilation fails.
    #
    # IMPORTANT: sinks require AST-level context, so we fail fast if solc is down.
    if sinks:
        _write_output(
            "ERROR: --sinks currently requires solc AST parsing. Solc failed, and Slither fallback doesn't support sinks yet.\n"
            "Tip: provide a working solc via --solc or SCARLET_SOLC (e.g. --solc /usr/bin/solc).\n",
            out,
        )
        raise typer.Exit(code=2)

    if resolved_solc:
        sys.stderr.write(f"solc resolved to: {resolved_solc}\n")
    sys.stderr.flush()

    spinner = Spinner(enabled=not no_progress)
    spinner.start("Indexing via Slither...")

    # IMPORTANT:
    # Slither works best when pointed at a project root (foundry/hardhat) or a single entry .sol.
    # Here we pass the user's scope path (file or dir) rather than individual files list.
    scope_path = Path(scope).expanduser().resolve()

    # Pick a valid Slither entry:
    # - if scope is a file and endswith .sol -> use that
    # - if scope is a directory -> use it
    # - if scope is a .txt list -> use the nearest foundry root (or parent of first file)
    if scope_path.is_file() and scope_path.suffix == ".sol":
        entry = scope_path
    elif scope_path.is_dir():
        entry = scope_path
    else:
        # scope is likely a .txt list (or something else); use parent of first scoped file
        first = files[0]
        entry = _find_foundry_root(first)

    contracts = build_index_with_slither(entry)


    # --- filter slither results to files in scope ---
    # Slither may pull in dependencies outside the requested scope (e.g., lib/ or
    #   remapped packages). Strictly re-apply the user's scope at the end so the
    #   report doesn't unexpectedly include third-party code and so file lists stay
    #   reproducible between machines.
    allowed = {str(p.resolve()) for p in files}

    contracts = [
        c for c in contracts
        if c.file and str(Path(c.file).resolve()) in allowed
    ]

    eps = []
    if entrypoints:
        src_by_file = {}
        for c in contracts:
            if not c.file:
                continue
            try:
                src_by_file[c.file] = Path(c.file).read_text(encoding="utf-8")
            except Exception:
                src_by_file[c.file] = ""

        eps = collect_entrypoints(contracts=contracts, src_by_file=src_by_file)

        # filter noise: contracts only
        eps = [ep for ep in eps if (ep.contract_kind or "").lower() == "contract"]
        # NOTE: Slither-based entrypoints are inherently heuristic:
        #   SCARLET reconstruct "entrypointness" from Slither metadata + source text,
        #   which can be slightly off for generated code / unusual formatting.
        # Keeping this explicit helps users interpret results correctly.

    if not full:
        contracts = [
            type(c)(
                name=c.name,
                kind=c.kind,
                file=c.file,
                functions=[f for f in c.functions if f.visibility in ("public", "external")],
                has_receive=c.has_receive,
                has_fallback=c.has_fallback,
            )
            for c in contracts
        ]
        # full=False is a UI choice: the default report is meant to highlight
        #   externally reachable surface area. Internal/private functions often
        #   explode report size without helping initial triage.
    
    # drop empty contracts
    contracts = [c for c in contracts if c.functions]

    spinner.stop()

    payload = {
        "directory": str(scope_dir),
        "files": [p.as_posix() for p in files],
        "contracts": [
            {
                "name": c.name,
                "kind": c.kind,
                "file": c.file,
                "functions": [
                    {
                        "name": f.name,
                        "signature": f.signature,
                        "visibility": f.visibility,
                        "mutability": f.mutability,
                        "modifiers": f.modifiers,
                        "line": f.line,
                    }
                    for f in c.functions
                ],
                "has_receive": c.has_receive,
                "has_fallback": c.has_fallback,
            }
            for c in contracts
        ],
    }

    if entrypoints:
        payload["entrypoints"] = [
            {
                "contract": ep.contract,
                "contract_kind": ep.contract_kind,
                "file": ep.file,
                "signature": ep.signature,
                "name": ep.name,
                "visibility": ep.visibility,
                "mutability": ep.mutability,
                "modifiers": ep.modifiers,
                "line": ep.line,
                "tags": ep.tags,
            }
            for ep in eps
        ]


    payload["contracts"] = _filter_contracts_for_output(
        payload.get("contracts", []),
        include_libraries=include_libraries,
        include_interfaces=include_interfaces,
    )

    try:
        if fmt == "json":
            _write_output(json.dumps(payload, indent=2, ensure_ascii=False), out)
        else:
            if entrypoints:
                _write_output(render_entrypoints_md_from_dict(payload), out)
            else:
                _write_output(render_index_md_from_dict(payload), out)

    except Exception as e:
        sys.stderr.write(f"Render failed: {type(e).__name__}: {e}\n")
        sys.stderr.flush()
        raise typer.Exit(code=3)

def main():
    app()

if __name__ == "__main__":
    main()
