from __future__ import annotations

from ..indexer import IndexReport, ContractInfo, FunctionInfo


def _fmt_fn(fi: FunctionInfo) -> str:
    vis = fi.visibility or "unknown"
    mut = fi.mutability or ""
    suffix = f" [{vis}{(' ' + mut) if mut else ''}]"
    return f"- `{fi.signature}`{suffix} — line {fi.line}"


def render_index_md(report: IndexReport) -> str:
    lines: list[str] = []
    lines.append("# SCARLET Index Report")
    lines.append("")
    lines.append("## Directory")
    lines.append(f"`{report.directory}`")
    lines.append("")
    lines.append("## Files")
    for f in report.files:
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Contracts")
    if not report.contracts:
        lines.append("_No contracts found._")
        lines.append("")
        return "\n".join(lines)

    for c in report.contracts:
        lines.append(f"### {c.name} ({c.kind})")
        lines.append(f"- file: `{c.file}`")
        lines.append(f"- receive(): {'✅' if c.has_receive else '❌'}")
        lines.append(f"- fallback(): {'✅' if c.has_fallback else '❌'}")
        lines.append("")
        lines.append("**Functions**")
        for fn in c.functions:
            lines.append(_fmt_fn(fn))
        lines.append("")

    return "\n".join(lines)

def render_index_md_from_dict(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# SCARLET Index Report")
    lines.append("")
    lines.append("## Directory")
    lines.append(f"`{payload.get('directory','')}`")
    lines.append("")
    lines.append("## Files")
    for f in payload.get("files", []):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Contracts")
    contracts = payload.get("contracts", [])
    if not contracts:
        lines.append("_No contracts found._")
        return "\n".join(lines)

    for c in contracts:
        lines.append(f"### {c.get('name')} ({c.get('kind','contract')})")
        lines.append(f"- file: `{c.get('file','')}`")
        lines.append(f"- receive(): {'✅' if c.get('has_receive') else '❌'}")
        lines.append(f"- fallback(): {'✅' if c.get('has_fallback') else '❌'}")
        lines.append("")
        lines.append("**Functions**")
        for fn in c.get("functions", []):
            sig = fn.get("signature", "")
            vis = fn.get("visibility", "unknown")
            mut = fn.get("mutability", "")
            line_no = fn.get("line", 1)
            suffix = f" [{vis}{(' ' + mut) if mut else ''}]"
            lines.append(f"- `{sig}`{suffix} — line {line_no}")
        lines.append("")
    return "\n".join(lines)
