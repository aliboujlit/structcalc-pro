# -*- coding: utf-8 -*-
"""
tools/probe_civil3d_nw_com.py — Sondage COM Civil 3D + Navisworks.

Contexte : la sonde large a révélé que
  - Civil 3D expose  AeccXUiLand.AeccApplication.13.9  (mon premier scan le
    manquait : il exigeait le préfixe "Aecc." exact et ratait "AeccX...") ;
  - Navisworks expose Navisworks.Document -> Roamer.exe.

Étape 1 (lecture registre, AUCUN lancement) : type de serveur (Inproc/Local),
chemin, ProgID indépendant de version.
Étape 2 (activation réelle) : tentative COM avec gestion du délai, puis
interrogation des membres exposés. Aucune méthode n'est supposée.

Usage : python tools/probe_civil3d_nw_com.py [--activate]
"""
from __future__ import annotations

import json
import sys
import time

try:
    import winreg
    HAS = True
except ImportError:  # pragma: no cover
    HAS = False

TARGETS = (
    "AeccXUiLand.AeccApplication.13.9",
    "AeccXUiLand.AeccApplication",
    "AeccXUiLand.AeccDocument.13.9",
    "AeccXUiPipe.AeccPipeApplication.13.9",
    "Navisworks.Document",
    "Navisworks.Document.24",
    "NavisworksIntegratedAPI.nwUtilityObject",
)


def _val(k, name=""):
    try:
        return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def registry_info() -> dict:
    """Type de serveur + chemin pour chaque ProgID cible (lecture seule)."""
    out: dict = {}
    if not HAS:
        return {"error": "winreg indisponible"}
    for pid in TARGETS:
        info: dict = {"found": False}
        try:
            k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, pid + r"\CLSID")
            clsid = _val(k)
            k.Close()
            info["clsid"] = clsid
            info["found"] = True
        except OSError:
            out[pid] = info
            continue
        # ProgID indépendant de version ?
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, pid.rsplit(".", 1)[0] + r"\CLSID")
            info["viprogid"] = pid.rsplit(".", 1)[0]
            k.Close()
        except OSError:
            info["viprogid"] = None
        # Serveur
        for sub in ("InprocServer32", "LocalServer32"):
            try:
                k = winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\{sub}")
                info["server_kind"] = sub
                info["server_path"] = _val(k)
                info["threading"] = _val(k, "ThreadingModel")
                k.Close()
                break
            except OSError:
                continue
        out[pid] = info
    return out


def activate(progids) -> dict:
    """Tentative d'activation COM réelle (peut lancer l'application)."""
    import pythoncom
    import win32com.client

    results: dict = {}
    pythoncom.CoInitialize()
    for pid in progids:
        entry: dict = {"ok": False}
        t0 = time.time()
        # 1) rattachement à une instance existante
        try:
            obj = win32com.client.GetActiveObject(pid)
            entry["method"] = "GetActiveObject"
            entry["obj"] = obj
        except Exception as exc:
            entry["attach_err"] = f"{type(exc).__name__}"
            obj = None
        # 2) création / lancement
        if obj is None:
            try:
                obj = win32com.client.Dispatch(pid)
                entry["method"] = "Dispatch"
                entry["obj"] = obj
            except Exception as exc:
                entry["dispatch_err"] = f"{type(exc).__name__}: {exc}"[:180]
        if obj is None:
            entry["elapsed"] = round(time.time() - t0, 1)
            # ne conserver que les erreurs (pas l'objet)
            results[pid] = {k: v for k, v in entry.items() if k != "obj"}
            continue
        # 3) interroger les membres réellement exposés (aucune méthode supposée)
        try:
            entry["type"] = type(obj).__name__
            entry["members"] = sorted(
                m for m in dir(obj) if not m.startswith("_"))[:40]
        except Exception as exc:
            entry["members_err"] = f"{type(exc).__name__}"
        # 4) propriétés simples non destructrices si présentes
        for attr in ("Name", "Version", "Caption", "Visible", "Count"):
            try:
                v = getattr(obj, attr)
                if not callable(v):
                    entry.setdefault("props", {})[attr] = repr(v)[:60]
            except Exception:
                pass
        entry["ok"] = True
        entry["elapsed"] = round(time.time() - t0, 1)
        results[pid] = {k: v for k, v in entry.items() if k != "obj"}
    pythoncom.CoUninitialize()
    return results


def main() -> int:
    do_act = "--activate" in sys.argv
    print("=" * 74)
    print("SONDAGE COM — Civil 3D (AeccX*) + Navisworks")
    print("=" * 74)

    print("\n[1] REGISTRE (lecture seule, aucun lancement)")
    reg = registry_info()
    if "error" in reg:
        print("   ", reg["error"])
        return 1
    for pid, info in reg.items():
        if info.get("found"):
            print(f"    TROUVÉ  {pid}")
            print(f"            clsid={info.get('clsid')}")
            print(f"            serveur={info.get('server_kind')} "
                  f"threading={info.get('threading')}")
            print(f"            path={info.get('server_path')}")
            print(f"            viprogid={info.get('viprogid')}")
        else:
            print(f"    absent  {pid}")

    if do_act:
        print("\n[2] ACTIVATION RÉELLE (peut lancer une application)")
        todo = [p for p, i in reg.items() if i.get("found")]
        res = activate(todo)
        for pid, info in res.items():
            print(f"\n    --- {pid} ---")
            for k, v in info.items():
                if k == "members":
                    print(f"        members ({len(v)}): {v}")
                else:
                    print(f"        {k}: {v}")
        print("\n" + "=" * 74)
        print("JSON:\n" + json.dumps(res, indent=2, ensure_ascii=False,
                                     default=str))
    else:
        print("\n(passer --activate pour tenter l'activation COM réelle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
