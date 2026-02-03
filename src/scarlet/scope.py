from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ScopeResult:
    included: list[Path]
    excluded: list[Path]
    final: list[Path]

def _read_path_list(txt_path: Path) -> list[Path]:
    """
    Read a .txt list of paths. Relative paths are resolved relative to the .txt file location.
    Lines starting with # and empty lines are ignored.
    """
    base = txt_path.parent
    out: list[Path] = []

    for raw in txt_path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue

        p = Path(s)
        if not p.is_absolute():
            p = base / p

        out.append(p.expanduser().resolve())

    return out

def _read_txt_list(txt_path: Path) -> list[Path]:
    """
    Reads a .txt file with paths. Rules:
    - empty lines ignored
    - lines starting with # ignored
    - trims whitespace
    - relative paths resolved relative to the .txt file location
    """
    base = txt_path.parent
    items: list[Path] = []
    for raw in txt_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        if not p.is_absolute():
            p = (base / p).resolve()
        else:
            p = p.resolve()
        items.append(p)
    return items


def _collect_sol_files_in_dir(root: Path) -> list[Path]:
    # recursive .sol
    files = [p.resolve() for p in root.rglob("*.sol") if p.is_file()]
    files.sort()
    return files


def resolve_scope(scope: str | Path | None) -> list[Path]:
    """
    Returns a sorted list of .sol files from:
    - .sol file
    - directory (recursive)
    - .txt list (paths to files/dirs)
    """
    if scope is None:
        raise ValueError("Scope is required")

    p = Path(scope).expanduser()
    if not p.is_absolute():
        p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(f"Scope path does not exist: {p}")

    if p.is_dir():
        return _collect_sol_files_in_dir(p)

    if p.is_file():
        if p.suffix.lower() == ".sol":
            return [p.resolve()]

        if p.suffix.lower() == ".txt":
            # .txt can contain files and/or directories
            items = _read_txt_list(p)
            out: list[Path] = []
            for item in items:
                if item.is_dir():
                    out.extend(_collect_sol_files_in_dir(item))
                elif item.is_file() and item.suffix.lower() == ".sol":
                    out.append(item.resolve())
            out = sorted(set(out))
            return out

    # if it's a file but not .sol/.txt, treat as invalid for scope
    raise ValueError(f"Unsupported scope type: {p} (expected .sol, directory, or .txt)")


def subtract_out_of_scope(included: Iterable[Path], out_of_scope: str | Path | None) -> ScopeResult:
    included_set = {p.resolve() for p in included}

    if out_of_scope is None:
        final = sorted(included_set)
        return ScopeResult(included=sorted(included_set), excluded=[], final=final)

    excluded = resolve_scope(out_of_scope)
    excluded_set = {p.resolve() for p in excluded}

    final_set = included_set - excluded_set
    return ScopeResult(
        included=sorted(included_set),
        excluded=sorted(excluded_set),
        final=sorted(final_set),
    )
