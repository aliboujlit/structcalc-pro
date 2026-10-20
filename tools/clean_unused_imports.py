# -*- coding: utf-8 -*-
"""
tools/clean_unused_imports.py — Nettoyage des imports inutilisés.

Supprime (ou réduit) les imports morts détectés par AST, sans toucher aux
re-exports de __init__.py (légitimes via __all__).

Usage : python tools/clean_unused_imports.py [--apply]
Sans --apply : mode rapport uniquement (dry-run).
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "structcalc", "architectural_structural")


def collect(src: str):
    tree = ast.parse(src)
    imported = {}  # name -> (lineno, import_keyword, is_from, module, parts)
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                nm = (a.asname or a.name).split(".")[0]
                imported[nm] = {
                    "lineno": n.lineno,
                    "is_from": isinstance(n, ast.ImportFrom),
                    "module": n.module if isinstance(n, ast.ImportFrom) else None,
                    "alias": a.name,
                    "asname": a.asname,
                }
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            b = n
            while isinstance(b, ast.Attribute):
                b = b.value
            if isinstance(b, ast.Name):
                used.add(b.id)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            # __all__ listes de chaînes -> considérer comme utilisé
            pass
    # __all__ strings count as usage
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    if isinstance(n.value, (ast.List, ast.Tuple)):
                        for e in n.value.elts:
                            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                used.add(e.value)
    unused = sorted(nm for nm in imported
                    if nm not in used and nm != "annotations")
    return imported, unused


def clean_file(path: str, apply: bool) -> bool:
    src = open(path, encoding="utf-8").read()
    imported, unused = collect(src)
    if not unused:
        return False
    lines = src.splitlines(True)
    drop_lines = {}
    for nm in unused:
        drop_lines.setdefault(imported[nm]["lineno"], []).append(nm)

    final = []
    changed = False
    for i, line in enumerate(lines, start=1):
        if i not in drop_lines:
            final.append(line)
            continue
        changed = True
        names = drop_lines[i]
        m = re.match(r"^(\s*)(from\s+\S+\s+import\s+)(.*)$", line)
        if m and ("," in m.group(3) or " as " in m.group(3)):
            indent, kw, parts = m.groups()
            keep = []
            for p in [x.strip() for x in parts.split(",")]:
                if not p:
                    continue
                base = p.split(" as ")[-1].strip()
                if base in names:
                    continue
                keep.append(p)
            if keep:
                final.append(f"{indent}{kw}{', '.join(keep)}\n")
                continue
        # ligne entièrement à supprimer
        if line.strip().endswith(","):
            # gérer les imports multi-lignes débutants : rien à faire ici
            pass
    new = "".join(final)
    if changed and new != src:
        if apply:
            open(path, "w", encoding="utf-8").write(new)
        return True
    return False


def main() -> int:
    apply = "--apply" in sys.argv
    touched = []
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        p = os.path.join(ROOT, f)
        try:
            if clean_file(p, apply):
                touched.append(f)
        except SyntaxError as e:
            print(f"ERREUR {f}: {e}")
    if touched:
        print(("APPLIQUÉ : " if apply else "DRY-RUN : ") +
              ", ".join(touched))
    else:
        print("Rien à nettoyer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
