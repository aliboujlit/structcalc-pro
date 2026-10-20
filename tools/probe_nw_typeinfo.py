# -*- coding: utf-8 -*-
"""
tools/probe_nw_typeinfo.py — Enumération FIDELE des membres COM Navisworks.

Ma sonde précédente utilisait une signature GetIDsOfNames erronée et marquait
tout « absent ». Ici on interroge ITypeInfo (GetFuncDesc/GetNames) : c'est la
source de vérité du COM. Aucune méthode n'est supposée, toutes sont lues.

Usage : python tools/probe_nw_typeinfo.py
"""
from __future__ import annotations

import time

TARGETS = (
    ("Navisworks.Document.24", "Local -> Roamer.exe"),
    ("NavisworksIntegratedAPI.nwUtilityObject.24", "Inproc -> lcodieD.dll"),
    ("NavisworksIntegratedAPI.nwControlSDI.24", "Inproc -> lcodieD.dll"),
    ("NavisworksIntegratedAPI.nwOpState.24", "Inproc -> lcodieD.dll"),
)


def typeinfo_members(obj):
    """Lit ITypeInfo : noms réels des fonctions + coclass."""
    import pythoncom
    out = {"funcs": [], "props": [], "coclass": None, "guid": None}
    try:
        ole = obj._oleobj_
    except AttributeError:
        out["err"] = "pas de _oleobj_"
        return out
    try:
        ti = ole.GetTypeInfo()
    except Exception as exc:
        out["err"] = "GetTypeInfo: " + type(exc).__name__
        return out
    try:
        attr = ti.GetTypeAttr()
        out["guid"] = str(attr.guid)
        out["typekind"] = int(attr.typekind)
        if int(attr.typekind) == pythoncom.TKIND_COCLASS:
            for i in range(attr.cImplTypes):
                flags = ti.GetImplTypeFlags(i)
                hr, ref = ti.GetRefTypeOfImplType(i)
                t2 = ti.GetRefTypeInfo(ref)
                nm = t2.GetDocumentation(-1)[0]
                out.setdefault("ifaces", []).append({
                    "name": nm,
                    "flags": int(flags),
                    "source": bool(int(flags) & pythoncom.IMPLTYPEFLAG_FSOURCE),
                    "default": bool(int(flags) & pythoncom.IMPLTYPEFLAG_FDEFAULT),
                })
        for i in range(attr.cFuncs):
            fd = ti.GetFuncDesc(i)
            try:
                names = ti.GetNames(fd.memid)
            except Exception:
                names = ["?"]
            kind = int(getattr(fd, "invkind", 0))
            label = {1: "method", 2: "get", 4: "put"}.get(kind, str(kind))
            out["funcs"].append({
                "name": names[0],
                "kind": label,
                "params": len(names) - 1,
                "all": list(names),
            })
    except Exception as exc:
        out["err"] = "typeattr: " + type(exc).__name__ + ": " + str(exc)
    return out


def try_target(pid, label):
    import pythoncom
    import win32com.client
    info = {"progid": pid, "label": label}
    t0 = time.time()
    pythoncom.CoInitialize()
    try:
        obj = win32com.client.Dispatch(pid)
        info["dispatch"] = True
    except Exception as exc:
        info["dispatch"] = False
        info["err"] = (type(exc).__name__ + ": " + str(exc))[:200]
        info["elapsed"] = round(time.time() - t0, 1)
        pythoncom.CoUninitialize()
        return info
    info["elapsed"] = round(time.time() - t0, 1)
    info.update(typeinfo_members(obj))
    readable = {}
    for a in ("Name", "Version", "Caption", "Visible", "FileName", "FullName",
              "Path", "ActiveDocument", "Documents", "Items", "Count", "Value"):
        try:
            v = getattr(obj, a)
            if not callable(v):
                readable[a] = repr(v)[:70]
        except Exception:
            pass
    info["readable"] = readable
    pythoncom.CoUninitialize()
    return info


def main():
    print("=" * 74)
    print("ITypeInfo NAVISWORKS - membres reellement exposes")
    print("=" * 74)
    results = []
    for pid, label in TARGETS:
        print("")
        print("--- " + pid + "  [" + label + "]")
        r = try_target(pid, label)
        results.append(r)
        if not r.get("dispatch"):
            print("    Dispatch KO : " + str(r.get("err")))
            continue
        if r.get("err"):
            print("    typeinfo KO : " + str(r["err"]))
        print("    guid=" + str(r.get("guid")) + " kind=" + str(r.get("typekind")))
        if r.get("ifaces"):
            print("    interfaces :")
            for it in r["ifaces"]:
                tag = ""
                if it["source"]:
                    tag += " [SOURCE/evenements]"
                if it["default"]:
                    tag += " [defaut]"
                print("        " + it["name"] + tag)
        if r.get("funcs"):
            print("    " + str(len(r["funcs"])) + " fonctions :")
            for f in sorted(r["funcs"], key=lambda x: (x["kind"], x["name"])):
                print("        [" + f["kind"].ljust(6) + "] " + f["name"]
                      + "  (" + str(f["params"]) + " params)")
        if r.get("readable"):
            print("    lisibles : " + str(r["readable"]))

    print("")
    print("=" * 74)
    print("SYNTHESE DES CAPACITES OBSERVEES")
    print("=" * 74)
    for r in results:
        if r.get("dispatch") and r.get("funcs"):
            ms = [f["name"] for f in r["funcs"]]
            print("  " + r["progid"] + " : " + str(len(ms)) + " membres")
            interesting = sorted(set(m for m in ms if any(
                t in m.lower() for t in
                ("open", "save", "load", "file", "export", "model", "document",
                 "item", "select", "propert", "clash", "version"))))
            if interesting:
                print("      pertinents : " + str(interesting))
        elif r.get("dispatch"):
            print("  " + r["progid"] + " : dispatch OK mais typeinfo illisible")
        else:
            print("  " + r["progid"] + " : KO " + str(r.get("err", ""))[:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
