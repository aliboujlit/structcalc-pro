# -*- coding: utf-8 -*-
"""
tools/gen_combos_doc.py — Genere docs/COMBINAISONS_ET_DEMARCHES.md
depuis le module source structcalc/integration/interop/combinaisons.py
(une seule source de verite — le doc ne peut pas deriver du code).

Usage : python tools/gen_combos_doc.py
"""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from structcalc.integration.interop.combinaisons import (  # noqa: E402
    all_pairs, WORKFLOWS, INDUSTRY_CASES, SOFTWARE_NAMES, LABELS,
    reciprocal_pairs_count, inventory,
)
from structcalc.integration.interop.loop import (  # noqa: E402
    PROFILES, MISSION_LABELS,
)

OUT = ROOT / "docs" / "COMBINAISONS_ET_DEMARCHES.md"


def main() -> int:
    inv = inventory()
    lines: list[str] = []
    a = lines.append
    a("# STRUCTCALC PRO — Combinaisons, démarches et cas d'industrie")
    a("")
    a("> Document **généré** par `tools/gen_combos_doc.py` depuis")
    a("> `structcalc/integration/interop/combinaisons.py` (source unique).")
    a("> La faisabilité **réelle** de chaque liaison est évaluée par le hub")
    a("> selon les capacités vérifiées — un refus est toujours motivé")
    a("> (spec §19/§20) : rien n'est présenté comme disponible sans preuve.")
    a("")
    a(f"**Synthèse** : {len(SOFTWARE_NAMES)} logiciels — "
      f"**{inv.n_senses} sens dirigés** (A → B) — "
      f"**{inv.n_reciprocal} paires réciproques** — "
      f"**{len(WORKFLOWS)} démarches** — **{len(INDUSTRY_CASES)} cas "
      f"d'industrie**.")
    a("")
    a("---")
    a("")
    a("## 0. Les 6 logiciels et leur mission conçue")
    a("")
    a("| Logiciel | Mission conçue | Opérations réelles |")
    a("|---|---|---|")
    for name in SOFTWARE_NAMES:
        p = PROFILES[name]
        a(f"| {LABELS[name]} | {MISSION_LABELS[p.mission]} | "
          f"`{'`, `'.join(p.designed_ops)}` |")
    a("")
    a("---")
    a("")
    a("## 1. Combinaisons dirigées — les 30 sens (A → B via pivot SC-*)")
    a("")
    a("| # | Sens | Ce qui circule (source) | Ce que la cible en fait (mission) | Démarche bureau d'études |")
    a("|---|---|---|---|---|")
    for i, p in enumerate(all_pairs(), start=1):
        a(f"| {i} | **{p.source} → {p.target}** | {p.transfer} | "
          f"{p.target_action} | {p.use_case} |")
    a("")
    a(f"Les 30 sens = **{reciprocal_pairs_count()} paires réciproques** "
      "(chaque paire dans les deux sens, garantie par le pivot SC-*).")
    a("")
    a("---")
    a("")
    a("## 2. Démarches (workflows de bureau d'études)")
    a("")
    for w in WORKFLOWS:
        a(f"### {w.name}")
        a("")
        a(f"- **Clé** : `{w.key}`")
        a(f"- **Chaîne** : `{w.chain_labels}`"
          f" ({'boucle fermée' if w.loop else 'chemin ouvert'})")
        a(f"- **Objectif** : {w.objective}")
        a(f"- **Cas industrie** : {w.industry_case}")
        if w.notes:
            a(f"- **Note honnête** : {w.notes}")
        a(f"- **Jambages** : " + ", ".join(f"`{s}→{t}`" for s, t in w.legs))
        a("")
    a("---")
    a("")
    a("## 3. Cas d'industrie (bureau d'études / technologies)")
    a("")
    for c in INDUSTRY_CASES:
        a(f"### {c.name}")
        a("")
        a(f"- **Clé** : `{c.key}`")
        a(f"- **Logiciels mobilisés** : {c.software_labels}")
        a(f"- **Démarches** : " + ", ".join(f"`{k}`" for k in c.workflows))
        a(f"- **Livrables** : " + " ; ".join(c.deliverables))
        a(f"- **Réalité technique** : {c.reality}")
        a("")
    a("---")
    a("")
    a("## 4. Lecture des faisabilités")
    a("")
    a("| Statut affiché | Sens |")
    a("|---|---|")
    a("| `OK` | Route faisable selon capacités **vérifiées** "
      "(ex. AutoCAD ↔ Robot prouvé live) |")
    a("| `REFUS` + motif | Capacité absente/bloquée, **motif exact** "
      "affiché (ex. `revit.read_model=NOT_SUPPORTED` sans add-in .NET) |")
    a("| `—` | Même logiciel (route inutile) |")
    a("")
    a("Voir l'onglet **Combinaisons** de l'interface (matrice vivante) et")
    a("`python tools/demo_loop_missions.py` pour la boucle avec missions.")
    a("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print(f"genere : {OUT} ({len(lines)} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
