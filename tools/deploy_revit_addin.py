#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/deploy_revit_addin.py — Déploie l'add-in STRUCTCALC PRO vers Revit 2027.

Copie vers %APPDATA%\\Autodesk\\Revit\\Addins\\<année>\\ :
  - StructCalcAddin.dll    (add-in compilé)
  - StructCalcAddin.addin  (manifeste)
  - Newtonsoft.Json.dll    (référence Private=false : à copier à côté)

Usage :
  python tools/deploy_revit_addin.py [--configuration Release] [--revit-year 2027]
                                     [--no-build]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / "StructCalcAddin" / "StructCalcAddin"
REVIT_DIR = Path(r"C:\Program Files\Autodesk\Revit 2027")

# Découverte multi-chemins du SDK .NET (LOCALAPPDATA d'abord : install hors admin)
DOTNET_CANDIDATES = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "dotnet" / "dotnet.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "dotnet-sdk" / "dotnet.exe",
    Path(r"C:\Program Files\dotnet\dotnet.exe"),
    Path(r"C:\Program Files (x86)\dotnet\dotnet.exe"),
)


def find_dotnet() -> Path:
    """Chemin de l'exécutable dotnet (candidats + PATH)."""
    for cand in DOTNET_CANDIDATES:
        if cand.is_file():
            return cand
    found = shutil.which("dotnet")
    if found:
        return Path(found)
    raise RuntimeError(
        "SDK .NET introuvable. Installez .NET 10 SDK "
        "(https://dotnet.microsoft.com/download) ou précisez-le via PATH.")


def find_revit_addins_dir(year: int = 2027) -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("Variable APPDATA non définie")
    return Path(appdata) / "Autodesk" / "Revit" / "Addins" / str(year)


def build_addin(configuration: str = "Release") -> Path:
    """Compile le projet .NET (dotnet build, sortie bin/<config>/)."""
    csproj = PROJECT_DIR / "StructCalcAddin.csproj"
    if not csproj.exists():
        raise FileNotFoundError(f"Projet introuvable : {csproj}")

    dotnet = find_dotnet()
    print(f"Compilation : {dotnet} build {csproj.name} ({configuration})")
    proc = subprocess.run(
        [str(dotnet), "build", str(csproj), "-c", configuration, "--nologo"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-15:])
        raise RuntimeError(f"Échec de la compilation .NET :\n{tail}")

    output_dll = PROJECT_DIR / "bin" / configuration / "StructCalcAddin.dll"
    if not output_dll.exists():
        raise FileNotFoundError(f"DLL non générée : {output_dll}")
    return output_dll


def deploy_addin(addin_dir: Path, dll_path: Path, year: int) -> None:
    """Copie DLL + manifeste + Newtonsoft.Json.dll vers le dossier Revit."""
    addin_dir.mkdir(parents=True, exist_ok=True)
    configuration = "Release" if "Release" in str(dll_path) else "Debug"

    # 1. Add-in compilé
    shutil.copy2(dll_path, addin_dir / "StructCalcAddin.dll")
    print(f"OK DLL copied       : {addin_dir / 'StructCalcAddin.dll'}")

    # 2. Manifeste (source projet, pas la copie bin/)
    manifest = PROJECT_DIR / "StructCalcAddin.addin"
    shutil.copy2(manifest, addin_dir / "StructCalcAddin.addin")
    print(f"OK Manifest copied  : {addin_dir / 'StructCalcAddin.addin'}")

    # 3. Newtonsoft.Json.dll (référence Private=false : NON copiée dans bin/)
    newtonsoft = REVIT_DIR / "Newtonsoft.Json.dll"
    if newtonsoft.is_file():
        shutil.copy2(newtonsoft, addin_dir / "Newtonsoft.Json.dll")
        print(f"OK Newtonsoft.Json  : {addin_dir / 'Newtonsoft.Json.dll'}")
    else:
        print(f"WARNING : {newtonsoft} not found — add-in will fail to "
              f"load if Revit doesn't already provide the assembly.")

    print(f"\nAdd-in deployed for Revit {year} (build {configuration}).")
    print("-> Restart Revit (or reopen a .rvt) to load the add-in.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Déploiement add-in STRUCTCALC PRO Revit")
    parser.add_argument("--configuration", default="Release",
                        choices=["Debug", "Release"])
    parser.add_argument("--revit-year", type=int, default=2027)
    parser.add_argument("--no-build", action="store_true",
                        help="Utiliser le binaire existant sans recompiler")
    args = parser.parse_args()

    try:
        if args.no_build:
            dll = PROJECT_DIR / "bin" / args.configuration / "StructCalcAddin.dll"
            if not dll.exists():
                print(f"ERREUR : binaire absent (relancez sans --no-build) : {dll}")
                return 1
        else:
            dll = build_addin(args.configuration)
        deploy_addin(find_revit_addins_dir(args.revit_year), dll,
                     args.revit_year)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERREUR : {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
