# -*- coding: utf-8 -*-
"""
probe_robot_signature.py — Phase 0 : introspection des signatures COM.

Pour éviter de deviner les appels, lit la vraie signature (paramètres, types)
des méthodes clés via ITypeInfo. Aucun appel exécuté, aucune modification.

Méthodes inspectées : Project.New, Project.NewFromTemplate, Project.Open,
Project.ActiveModel, Model.Bars.Create, Model.Nodes.Create.
"""

import os
import json
import pythoncom
import comtypes.client

TLB = (r"C:\Program Files\Autodesk\Robot Structural Analysis Professional "
       r"2027\Exe\robotom.tlb")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "robot_signatures.json")

# Types COM -> lisibles
VT = {
    0: "EMPTY", 1: "NULL", 2: "I2", 3: "I4", 4: "R4", 5: "R8", 6: "CY",
    7: "DATE", 8: "BSTR", 9: "DISPATCH", 10: "ERROR", 11: "BOOL",
    12: "VARIANT", 13: "UNKNOWN", 14: "DECIMAL", 16: "I1", 17: "UI1",
    18: "UI2", 19: "UI4", 20: "I8", 21: "UI4", 22: "INT", 23: "UINT",
    24: "VOID", 25: "HRESULT", 26: "PTR", 27: "SAFEARRAY", 28: "CARRAY",
    29: "USERDEFINED", 30: "LPSTR", 31: "LPWSTR", 36: "RECORD",
    37: "INT_PTR", 38: "UINT_PTR",
}


def vt_name(vt):
    base = vt & 0xFFFF
    name = VT.get(base, f"VT_{base}")
    if vt & pythoncom.VT_ARRAY:
        name = "ARRAY|" + name
    if vt & pythoncom.VT_BYREF:
        name = "REF|" + name
    return name


def describe_func(typeinfo, func_index):
    """Décris une fonction COM : nom, params, types."""
    try:
        funcdesc = typeinfo.GetFuncDesc(func_index)
    except Exception:
        return None
    names = typeinfo.GetNames(funcdesc.memid)
    params = []
    # GetNames : [nom_retour?, nom_param1, ...] selon convention
    param_names = list(names)
    invkind = funcdesc.invkind

    for i, pd in enumerate(funcdesc.lprgelemdescParam or []):
        try:
            vt = pd.tdesc.vt
        except Exception:
            vt = None
        params.append({
            "index": i,
            "vt": vt_name(vt) if vt is not None else "?",
            "inout": "in" if (pd.paramdesc.wParamFlags & 1) else "opt/in",
        })
    return {
        "names": param_names,
        "invkind": int(invkind),
        "param_count": int(funcdesc.cParams),
        "params": params,
        "optional_params": int(getattr(funcdesc, "cParamsOpt", -1)),
    }


def inspect_coclass(tlb, coclass_name):
    """Trouve l'interface par défaut d'une coclass et liste ses membres."""
    coclass = getattr(tlb, coclass_name, None)
    if coclass is None:
        return {"error": f"coclass {coclass_name} introuvable"}
    try:
        clsid = coclass._reg_clsid_
    except Exception:
        clsid = None

    # Récupérer ITypeInfo via le typelib du module
    try:
        typelib = coclass._com_get_nfo if False else None
    except Exception:
        typelib = None

    # Approche fiable : interroger le typelib généré
    info = {"coclass": coclass_name, "clsid": str(clsid), "members": {}}

    # Utilise l'interface par défaut (souvent nommée I<Name> ou <Name>)
    for cand in (f"I{coclass_name}", coclass_name):
        iface = getattr(tlb, cand, None)
        if iface is None:
            continue
        try:
            # Le module généré expose _methods_ avec des infos
            methods = getattr(iface, "_methods_", None)
            if methods:
                info["interface"] = cand
                info["method_names"] = [m[2] if len(m) > 2 else str(m)
                                        for m in methods][:80]
                return info
        except Exception:
            continue
    return info


def main():
    print("Chargement RobotOM...")
    RobotOM = comtypes.client.GetModule(TLB)

    out = {"tlb": TLB, "inspections": {}}

    # 1) Lister les symboles "Project"-liés disponibles
    proj_syms = [s for s in dir(RobotOM) if "Project" in s]
    print(f"Symboles 'Project' dans RobotOM : {proj_syms[:20]}")
    out["project_symbols"] = proj_syms[:40]

    # 2) Décrire la coclass RobotProject + interface
    for cc in ("RobotProject", "IRobotProject", "RobotApplication",
               "RobotBarServer", "RobotNodeServer"):
        out["inspections"][cc] = inspect_coclass(RobotOM, cc)

    # 3) Tenter d'obtenir la vraie signature de Project.New en instanciant
    #    puis en interrogeant ITypeInfo de l'objet live.
    try:
        app = comtypes.client.CreateObject("Robot.Application", dynamic=True)
        proj = app.Project
        # Obtenir ITypeInfo de l'objet dispatch
        oleobj = proj._oleobj_
        typeinfo = oleobj.GetTypeInfo()
        typeattr = typeinfo.GetTypeAttr()
        out["project_live_typekind"] = int(typeattr.typekind)
        out["project_live_func_count"] = int(typeattr.cFuncs)

        # Parcourir toutes les fonctions et garder celles qui nous intéressent
        wanted = {"New", "NewFromTemplate", "Open", "ActiveModel", "Save",
                  "SaveAs", "Close", "IsActive"}
        found = []
        for idx in range(typeattr.cFuncs):
            d = describe_func(typeinfo, idx)
            if d and d["names"] and any(w in d["names"] for w in wanted):
                found.append(d)
        out["project_live_signatures"] = found

        print(f"\nProject : {typeattr.cFuncs} fonctions COM. Signatures clés :")
        for d in found:
            print(f"  {d['names']}  (cParams={d['param_count']}, "
                  f"opt={d['optional_params']})")
            for p in d["params"]:
                print(f"      param[{p['index']}] {p['vt']} {p['inout']}")

        # Fermer sans agir
        try:
            app.Quit()
        except Exception:
            pass
    except Exception as exc:
        out["live_error"] = str(exc)
        print(f"Erreur live : {exc}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSignatures écrites : {OUT}")


if __name__ == "__main__":
    main()
