# -*- coding: utf-8 -*-
"""
tools/probe_advsteel_activate.py — Activation du modèle objet Advance Steel.

Constat : AstorMain5.tlb expose le VRAI modèle objet acier
(AdvanceSteelApplication, Beam, Bolt, AstUI, ...) mais AUCUN ProgID standalone
n'est enregistré. On tente d'activer le coclass par son CLSID (via la TLB) :

  1. extraire le CLSID du coclass AdvanceSteelApplication depuis la TLB ;
  2. vérifier s'il est enregistré (InprocServer32/LocalServer32 -> DLL) ;
  3. tenter comtypes.CreateObject (peut échouer si contexte en-processus requis).

Aucune méthode supposée : on interroge la TLB et le registre, puis on tente.

Usage : python tools/probe_advsteel_activate.py
"""
from __future__ import annotations

import os
import sys

ADVS_DIR = r"C:\Program Files\Autodesk\AutoCAD 2027\ADVS"
TLB = os.path.join(ADVS_DIR, "AstorMain5.tlb")

CANDIDATES = ("AdvanceSteelApplication", "AstUI", "AstObjectsArr")

try:
    import winreg
    HAS = True
except ImportError:  # pragma: no cover
    HAS = False


def _v(k, name=""):
    try:
        return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def coclass_clsid(mod, name):
    """CLSID d'un coclass via comtypes (module généré depuis la TLB)."""
    obj = getattr(mod, name, None)
    if obj is None:
        return None, f"{name} absent du module"
    # comtypes : une coclass est une instance de _coclass_meta avec clsid
    clsid = getattr(obj, "_reg_clsid_", None)
    if clsid is None:
        # parfois la classe Python porte le CLSID via __dict__
        for attr in ("_clsid", "clsid", "__clsid__"):
            clsid = getattr(obj, attr, None)
            if clsid:
                break
    return obj, str(clsid) if clsid else None


def registry_for(clsid):
    """Serveur COM enregistré pour ce CLSID (lecture seule)."""
    if not HAS or not clsid:
        return None
    for sub in ("InprocServer32", "LocalServer32"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                rf"CLSID\{clsid}\{sub}") as k:
                return {"kind": sub, "path": str(_v(k)),
                        "threading": _v(k, "ThreadingModel")}
        except OSError:
            continue
    return None


def try_create(name):
    """Tentative d'activation via comtypes (peut lancer / échouer)."""
    import comtypes.client
    info = {}
    try:
        # GetModule produit un binding typé à partir de la TLB
        mod = comtypes.client.GetModule(TLB)
        obj = comtypes.client.CreateObject(
            getattr(mod, name), interface=None)
        info["ok"] = True
        info["type"] = type(obj).__name__
        readable = {}
        for a in ("Name", "Version", "Visible", "Application", "Document",
                  "Documents", "ActiveDocument"):
            try:
                v = getattr(obj, a)
                if not callable(v):
                    readable[a] = repr(v)[:60]
            except Exception:
                pass
        info["readable"] = readable
    except Exception as exc:
        info["ok"] = False
        info["err"] = f"{type(exc).__name__}: {exc}"[:180]
    return info


def main() -> int:
    print("=" * 74)
    print("ACTIVATION MODÈLE OBJET ADVANCE STEEL (AstorMain5.tlb)")
    print("=" * 74)
    if not os.path.isfile(TLB):
        print("TLB absente :", TLB)
        return 1

    import comtypes.client
    try:
        mod = comtypes.client.GetModule(TLB)
    except Exception as exc:
        print("GetModule KO :", type(exc).__name__, exc)
        return 1

    print("\n[1] CLSIDs des coclasses candidats")
    info_map = {}
    for name in CANDIDATES:
        obj, clsid = coclass_clsid(mod, name)
        info_map[name] = clsid
        print(f"    {name:<26} clsid={clsid}")

    print("\n[2] Registre (serveur enregistré ?)")
    for name, clsid in info_map.items():
        reg = registry_for(clsid)
        if reg:
            print(f"    {name}: {reg['kind']} -> "
                  f"{os.path.basename(reg['path'])} "
                  f"(threading={reg['threading']})")
        else:
            print(f"    {name}: NON enregistré (pas de serveur COM)")

    print("\n[3] Tentative CreateObject (contexte ?)")
    for name in CANDIDATES:
        info = try_create(name)
        if info["ok"]:
            print(f"    OK  {name} type={info['type']} "
                  f"readable={info.get('readable', {})}")
        else:
            print(f"    KO  {name} : {info['err']}")

    print("\n" + "=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
