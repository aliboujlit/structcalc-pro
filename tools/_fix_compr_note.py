# -*- coding: utf-8 -*-
"""Correction COMPR note (recherche exacte)."""
import io
import ast

p = r"structcalc\regulation\bael91r99\columns.py"
s = io.open(p, encoding="utf-8").read()

# Remplacer la note COMPR (recherche par code + verification_note actuelle)
old = '''            verification_note="Formule simplifiée = filtre initial uniquement "
                              "(spec §10.2). Vérifier c'''

new = '''            verification_note=("γc=1.5 / γs=1.15 CONFIRMÉS (recherche web + doctrine). "
                               "Coefficient 0.6 et formule Nr = 0.6·fcd·Ac + fyd·As CANDIDATS "
                               "— à confronter au fascicule officiel. fcd = fck/γc ; fyd = fyk/γs.")'''

s = s.replace(old, new)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
ast.parse(s)
print("COMPR corrigé, parse OK")