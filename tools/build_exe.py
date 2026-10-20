# -*- coding: utf-8 -*-
"""
tools/build_exe.py — Compilation du .exe STRUCTCALC PRO (PyInstaller).

Produit un exécutable AUTONOME (onefile, sans console) avec le numéro de
version EMBARQUE dans la ressource PE (version_info.txt, miroir de
structcalc/version.py) :

    dist\\STRUCTCALC_PRO_<version>.exe

Usage :
    python tools/build_exe.py                 # build Release
    python tools/build_exe.py --console       # build avec console (debug)
    python tools/build_exe.py --no-verify    # sauter l'autotest du .exe

Après build, un autotest automatique lance le .exe en mode
`--selftest` et lit %TEMP%\\structcalc_selftest.txt (SELFTEST=PASS requis).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # structcalc_pro\\
sys.path.insert(0, str(ROOT))

from structcalc.version import VERSION_STRING  # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXE_NAME = f"STRUCTCALC_PRO_{VERSION_STRING}"


def hidden_imports() -> list[str]:
    """Imports dynamiques que PyInstaller ne détecte pas statiquement.

    pywin32 (COM Robot/AutoCAD/Navisworks) + pywin32 pipe (client add-in
    Revit) sont importés tardivement dans le code (lazy) — on les
    déclare explicitement.
    """
    mods = [
        # pywin32 : COM dynamique (win32com.client.Dispatch/GetActiveObject)
        "pythoncom",
        "pywintypes",
        "win32com",
        "win32com.client",
        "win32com.server",
        "win32com.util",
        "win32com.restriction",
        "win32api",
        "win32process",
        "win32event",
        "win32file",
        "win32pipe",
        "win32security",
        # génération de bindings (robotom.tlb via comtypes, optionnel)
        "comtypes",
        "comtypes.gen",
        # paquets applicatifs chargés paresseusement
        "openpyxl",
        "reportlab",
    ]
    return mods


def run_pyinstaller(console: bool) -> None:
    import PyInstaller.__main__ as pyi

    args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        f"--name={EXE_NAME}",
        f"--version-file={ROOT / 'version_info.txt'}",
        f"--paths={ROOT}",
        f"--distpath={DIST}",
        f"--workpath={BUILD}",
        f"--specpath={BUILD}",
        # cache/exclusions propres
        "--exclude-module=matplotlib",
        "--exclude-module=numpy.f2py",
        "--exclude-module=PIL",
    ]
    if console:
        args.append("--console")
    else:
        args.append("--windowed")
    for m in hidden_imports():
        args.append(f"--hidden-import={m}")
    args.append(str(ROOT / "main.py"))

    print(f"[build] PyInstaller {__import__('PyInstaller').__version__} "
          f"-> {EXE_NAME}.exe (version {VERSION_STRING})")
    # PyInstaller >= 6 : point d'entree public = PyInstaller.__main__.run
    pyi.run(args)


def verify_exe(console: bool) -> bool:
    """Lance le .exe compilé en mode --selftest et lit le rapport."""
    exe = DIST / f"{EXE_NAME}.exe"
    if not exe.exists():
        print("[verify] ERREUR : exe introuvable", exe)
        return False

    report = Path(os.environ.get("TEMP", ".")) / "structcalc_selftest.txt"
    if report.exists():
        report.unlink()

    print(f"[verify] lancement {exe.name} --selftest …")
    creationflags = 0x00000008  # DETACHED_PROCESS (pas de console fantôme)
    proc = subprocess.Popen(
        [str(exe), "--selftest"],
        cwd=str(DIST),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if report.exists():
            # petite latence d'écriture
            time.sleep(1.0)
            break
        if proc.poll() is not None and not report.exists():
            time.sleep(1.0)
            if not report.exists():
                print("[verify] ERREUR : le .exe est sorti sans rapport "
                      f"(code {proc.returncode}).")
                return False
        time.sleep(0.5)
    else:
        proc.kill()
        print("[verify] ERREUR : délai dépassé (120 s).")
        return False

    if proc.poll() is None:
        proc.kill()
    text = report.read_text(encoding="utf-8", errors="replace")
    print("[verify] rapport autotest :")
    for line in text.splitlines():
        print("   ", line)
    ok = "SELFTEST=PASS" in text
    print("[verify]", "SUCCÈS" if ok else "ÉCHEC")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Build .exe STRUCTCALC PRO")
    ap.add_argument("--console", action="store_true",
                    help="build avec console (debug des erreurs)")
    ap.add_argument("--no-verify", action="store_true",
                    help="ne pas lancer l'autotest du .exe")
    ap.add_argument("--keep-dist", action="store_true",
                    help="ne pas nettoyer dist/ avant build")
    args = ap.parse_args()

    # Nettoyage ciblé des sorties précédentes
    if not args.keep_dist:
        for stale in (DIST / f"{EXE_NAME}.exe",):
            if stale.exists():
                stale.unlink()

    run_pyinstaller(console=args.console)

    exe = DIST / f"{EXE_NAME}.exe"
    if not exe.exists():
        print("[build] ERREUR : exe non généré.")
        return 1
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"[build] {exe} ({size_mb:.1f} Mo)")

    if args.no_verify:
        return 0

    return 0 if verify_exe(args.console) else 2


if __name__ == "__main__":
    raise SystemExit(main())
