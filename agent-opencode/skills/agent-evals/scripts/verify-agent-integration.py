#!/usr/bin/env python3
"""Generic agent integration verification gates for Python projects.

This script intentionally avoids framework-specific imports unless you pass them.
Exit code 0 means all enabled gates passed; 1 means at least one failed.
"""
import argparse
import ast
import py_compile
import re
import subprocess
import sys
from pathlib import Path


def gate_compile(src: Path) -> bool:
    print("\n=== Gate: Python compilation ===")
    ok = True
    files = list(src.rglob("*.py"))
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            print(f"FAIL {path}: {exc}")
            ok = False
    print(f"{'PASS' if ok else 'FAIL'} compiled {len(files)} files")
    return ok


def gate_config_contract(src: Path, config_file: str) -> bool:
    print("\n=== Gate: settings access contract ===")
    accesses: set[str] = set()
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        accesses.update(re.findall(r"get_settings\(\)\.(\w+)", text))
    cfg = src / config_file
    if not cfg.exists():
        print(f"SKIP no {cfg}")
        return True
    props = set(re.findall(r"@property\s+def\s+(\w+)\(", cfg.read_text(encoding="utf-8", errors="ignore")))
    missing = accesses - props
    if missing:
        print(f"FAIL missing settings properties: {sorted(missing)}")
        return False
    print(f"PASS {len(accesses)} settings accesses covered")
    return True


def gate_tool_wrapper_calls(src: Path) -> bool:
    print("\n=== Gate: direct decorated-tool calls ===")
    tool_names: set[str] = set()
    for path in src.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(getattr(dec, "id", "") == "tool" or getattr(getattr(dec, "func", None), "id", "") == "tool" for dec in node.decorator_list):
                    tool_names.add(node.name)
    violations: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "create_agent" in text or "bind_tools" in text:
            continue
        for name in tool_names:
            if re.search(rf"await\s+{re.escape(name)}\b\s*\(", text) and f"{name}.ainvoke" not in text:
                violations.append(f"{path}:{name}")
    if violations:
        print("FAIL direct tool wrapper calls:")
        for item in violations:
            print(f"  {item}")
        return False
    print(f"PASS checked {len(tool_names)} decorated tools")
    return True


def gate_import(import_expr: str | None) -> bool:
    if not import_expr:
        return True
    print("\n=== Gate: import/constructor smoke ===")
    result = subprocess.run([sys.executable, "-c", import_expr], text=True, capture_output=True)
    if result.returncode:
        print("FAIL", result.stderr or result.stdout)
        return False
    print("PASS", (result.stdout or "import expression succeeded").strip())
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="src", help="source directory to verify")
    parser.add_argument("--config-file", default="config.py", help="settings module path relative to --src")
    parser.add_argument("--import-smoke", help="Python expression to run, e.g. 'from app.agent import create_agent; create_agent()'")
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"ERROR: source directory not found: {src}", file=sys.stderr)
        return 2
    checks = [
        gate_compile(src),
        gate_config_contract(src, args.config_file),
        gate_tool_wrapper_calls(src),
        gate_import(args.import_smoke),
    ]
    passed = sum(checks)
    print(f"\nResults: {passed}/{len(checks)} gates passed")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
