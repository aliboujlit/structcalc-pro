# -*- coding: utf-8 -*-
"""
tools/probe_combination_sig.py — PROBE STATIQUE de la signature Robot
`Cases.CreateCombination` (spec §0 : aucune API inventée).

Charge robotom.tlb (ITypeLib) SANS lancer Robot, parcourt tous les types et
fonctions, et affiche la signature complète de tout membre nommé
CreateCombination (ainsi que l'interface Cases et Combinaisons associées).

Usage : python tools/probe_combination_sig.py
"""

import sys
import winreg

import comtypes.typeinfo as ti


def tlb_path() -> str:
    guid = "{F3A37BD0-AA2D-11D2-9844-0080C86BE4DF}"  # Robot Object Model 2027
    # sous-clé ...\\1.0\\0\\win32, valeur par défaut = chemin du .tlb
    key_path = "TypeLib\\" + guid + "\\1.0\\0\\win32"
    k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path)
    return winreg.QueryValue(k, "")


# InvKind des fonctions
_INVOKE_FUNC = 1
_INVOKE_PROPGET = 2
_INVOKE_PROPSET = 4


def vt_name(vt) -> str:
    """Nom lisible d'un variant type."""
    try:
        return ti.vartypeenum_to_string(vt)
    except Exception:
        return str(vt)


def main() -> int:
    path = tlb_path()
    print(f"TLB : {path}")
    tlb = ti.LoadTypeLib(path)
    n = tlb.GetTypeInfoCount()
    print(f"types : {n}")

    hits = []
    case_related = []
    for i in range(n):
        try:
            doc = tlb.GetDocumentation(i)
            tname = doc[0] if doc else "?"
        except Exception:
            tname = "?"
        try:
            tinfo = tlb.GetTypeInfo(i)
            attr = tinfo.GetTypeAttr()
        except Exception:
            continue
        nfunc = getattr(attr, "cFuncs", 0)
        for j in range(nfunc):
            try:
                fd = tinfo.GetFuncDesc(j)
            except Exception:
                continue
            try:
                fname = tinfo.GetDocumentation(fd.memid)[0]
            except Exception:
                fname = "?"
            # collecter tout ce qui touche aux combinaisons / Cases
            low = (tname + " " + fname).lower()
            if ("combination" in low or tname.lower().endswith("cases")
                    or "case" in tname.lower()):
                try:
                    names = tinfo.GetNames(fd.memid)
                except Exception:
                    names = [fname]
                inv = fd.invkind
                kind = ("method" if inv == _INVOKE_FUNC else
                        "propget" if inv == _INVOKE_PROPGET else
                        "propput" if inv == _INVOKE_PROPSET else str(inv))
                # noms (peut ne contenir que le nom de méthode si la TLB
                # n'expose pas les noms de paramètres)
                try:
                    names = tinfo.GetNames(fd.memid)
                except Exception:
                    names = [fname]
                # compte + types réels des paramètres (FUNCDESC)
                try:
                    cparams = int(fd.cParams)
                except Exception:
                    cparams = 0
                ptypes = []
                for k in range(cparams):
                    try:
                        ed = fd.lprgelemdescParam[k]
                        tdesc = ed.tdesc
                        vt = getattr(tdesc, "vt", None)
                        label = str(vt)
                        # résoudre VT_USERDEFINED (29) -> nom de type (énum)
                        if vt == 29:
                            try:
                                href = getattr(tdesc, "hreftype", None)
                                if href is None:
                                    href = getattr(tdesc, "_", None)
                                rt = tinfo.GetRefTypeInfo(href)
                                label = f"enum:{rt.GetDocumentation(0)[0]}"
                            except Exception as ex:
                                label = f"enum:<{ex}>"
                        # flags in/out/retval
                        try:
                            fl = int(ed.paramdesc.wParamFlags)
                            tags = []
                            if fl & 0x1: tags.append("in")
                            if fl & 0x2: tags.append("out")
                            if fl & 0x8: tags.append("retval")
                            if fl & 0x10: tags.append("lcid")
                            if fl & 0x20: tags.append("optional")
                            label += "[" + ",".join(tags) + "]"
                        except Exception:
                            pass
                        ptypes.append(label)
                    except Exception:
                        ptypes.append("?")
                sig = f"cParams={cparams} :: {ptypes}"
                entry = (tname, fname, kind, names, sig)
                if "createcombination" in fname.lower():
                    hits.append(entry)
                if ("combination" in tname.lower() or
                        "case" in tname.lower() or
                        "combination" in fname.lower()):
                    case_related.append(entry)
            # (fin filtre)

    print("\n=== CreateCombination (SIGNATURE CHERCHÉE) ===")
    if not hits:
        print("  AUCUN membre 'CreateCombination' trouvé dans la TLB.")
    for tname, fname, kind, names, sig in hits:
        print(f"  {tname}.{fname} [{kind}]")
        print(f"     noms   : {names}")
        print(f"     params : {sig}")

    print("\n=== Contexte : interfaces Cases / Combinaisons (extrait) ===")
    for tname, fname, kind, names, sig in case_related:
        if ("cases" in tname.lower() or "combination" in tname.lower()
                or "createcomb" in fname.lower()):
            print(f"  {tname}.{fname} [{kind}] params: {sig}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
