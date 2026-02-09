from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json

import os
os.environ["RICH_TRACEBACK"] = "0"

import sys
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

import typer

from .slither_index import build_index_with_slither
from .indexer import IndexReport, ContractInfo, FunctionInfo

from .scope import resolve_scope, subtract_out_of_scope
from .solc_ast import parse_ast
from .indexer import build_index, to_dict
from .report.md import render_index_md_from_dict #,render_index_md

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
    if out is None:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")

def _looks_like_script(path: str) -> bool:
    try:
        p = Path(path)
        if not p.exists():
            return False
        head = p.read_bytes()[:2]
        return head == b"#!"
    except Exception:
        return False

def _find_foundry_root(start: Path) -> Path:
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

@app.command()
def index(
    scope: str = typer.Option(..., "--scope", help="Scope: .sol file, directory, or .txt list of paths"),
    out_of_scope: Optional[str] = typer.Option(None, "--out-of-scope", "-oos", help="Exclude: .sol, directory, or .txt list"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write output to file instead of stdout"),
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

    included = resolve_scope(scope)
    scope_dir = Path(scope).expanduser().resolve()
    if scope_dir.is_file():
        scope_dir = scope_dir.parent

    scoped = subtract_out_of_scope(included, out_of_scope)
    files = scoped.final

    # --- Foundry default excludes (no need to pass -oos every time) ---
    if out_of_scope is None:
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
    spinner.start(f"Parsing with solc... Progress {len(files)}/{len(files)} files")

    # Resolve 'solc' to an actual path for diagnostics
    resolved_solc = shutil.which(solc) if solc == "solc" else solc

    ast_res = parse_ast(files, solc_bin=solc)
    spinner.stop()

    fatal_errors = [e for e in ast_res.errors if "error" in e.lower() or "fatal" in e.lower() or "compiler error" in e.lower()]

    if not fatal_errors:
        report = build_index(scope_dir=scope_dir, files=files, ast_res=ast_res)
        payload = to_dict(report)

        payload["contracts"] = _filter_contracts_for_output(
            payload.get("contracts", []),
            include_libraries=include_libraries,
            include_interfaces=include_interfaces,
        )

        if fmt == "json":
            _write_output(json.dumps(payload, indent=2, ensure_ascii=False), out)
        else:
            _write_output(render_index_md_from_dict(payload), out)

        raise typer.Exit(code=0)


    # --- Fallback: Slither path ---
    # If solc failed (e.g. 403 via solc-select), use Slither to build index.
    sys.stderr.write("Solc failed; falling back to Slither indexer.\n")
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
    allowed = {str(p.resolve()) for p in files}

    contracts = [
        c for c in contracts
        if c.file and str(Path(c.file).resolve()) in allowed
    ]

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

    payload["contracts"] = _filter_contracts_for_output(
        payload.get("contracts", []),
        include_libraries=include_libraries,
        include_interfaces=include_interfaces,
    )

    try:
        if fmt == "json":
            _write_output(json.dumps(payload, indent=2, ensure_ascii=False), out)
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
