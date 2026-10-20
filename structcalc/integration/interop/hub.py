# -*- coding: utf-8 -*-
"""
integration/interop/hub.py — Hub d'interconnexion RÉCIPROQUE Autodesk.

Demande utilisateur : « tout logiciel Autodesk peut se connecter avec les
autres, et de façon RÉCIPROQUE entre eux ».

Conception retenue (voir base.py) : ÉTOILE par pivot SC-*.

    Pour N logiciels, N connecteurs suffisent à obtenir les N×N sens :

        A --read-->  PIVOT  --write--> B      (A vers B)
        B --read-->  PIVOT  --write--> A      (B vers A)

    La réciprocité est ainsi garantie PAR CONSTRUCTION, sans écrire N² ponts
    directs (inassurables, §19).

Le hub fournit :
  - `registry`   : connexion/déconnexion des connecteurs ;
  - `routes()`   : matrice des routes POSSIBLES (avec raison si impossible) ;
  - `exchange()` : A -> pivot -> B avec rapports complets ;
  - `status()`   : inventaire honnête (installé / pilotable / capacités).

Aucune opération logicielle n'est simulée : une route impossible est
RETournée avec son motif, jamais levée en succès silencieux.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)


@dataclass
class RouteUnavailability:
    """Raison pour laquelle une route n'est pas exécutable."""
    source: str
    target: str
    reason: str
    missing: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target,
                "reason": self.reason, "missing": list(self.missing)}


@dataclass
class ExchangeResult:
    """
    Issue d'un échange A -> pivot -> B.

    `success` est True UNIQUEMENT si les deux demi-chemins ont réussi.
    Un demi-chemin refusé laisse `success=False` + `step_failed` renseigné.
    """
    source: str
    target: str
    success: bool
    step_failed: str = ""          # "" | "read" | "write"
    read_report: Optional[OpReport] = None
    write_report: Optional[OpReport] = None
    pivot_stats: Dict[str, int] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source, "target": self.target,
            "success": self.success, "step_failed": self.step_failed,
            "read": self.read_report.to_dict() if self.read_report else None,
            "write": self.write_report.to_dict() if self.write_report else None,
            "pivot_stats": dict(self.pivot_stats),
            "message": self.message,
        }


class InteropHub:
    """
    Registre + routeur des connecteurs Autodesk.

    Usage :
        hub = InteropHub()
        hub.register(AutoCADConnector())
        hub.register(RobotConnector())
        print(hub.status())               # inventaire honnête
        print(hub.routes())               # matrice de routes
        res = hub.exchange("robot", "autocad", project)   # réciproque OK
        res = hub.exchange("autocad", "robot", project)   # et l'inverse
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, AutodeskConnector] = {}

    # ------------------------------------------------------------------
    # Registre
    # ------------------------------------------------------------------
    def register(self, connector: AutodeskConnector) -> "InteropHub":
        if not connector.name or connector.name == "abstract":
            raise InteropError(
                "Connecteur sans nom stable : enregistrement refusé.")
        if connector.name in self._connectors:
            raise InteropError(
                f"Connecteur déjà enregistré : {connector.name!r} "
                f"(conflit de clé — §4.1 identifiants stables).")
        self._connectors[connector.name] = connector
        return self

    def unregister(self, name: str) -> None:
        self._connectors.pop(name, None)

    @property
    def names(self) -> List[str]:
        return sorted(self._connectors)

    def get(self, name: str) -> AutodeskConnector:
        if name not in self._connectors:
            raise InteropError(
                f"Connecteur inconnu : {name!r}. "
                f"Enregistrés : {self.names}")
        return self._connectors[name]

    # ------------------------------------------------------------------
    # Inventaire honnête
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, dict]:
        """Installé / transport / pilotable / capacités — sans complaisance."""
        out: Dict[str, dict] = {}
        for name, c in self._connectors.items():
            det = c.detect()
            caps = c.capabilities()
            out[name] = {
                "label": c.label or name,
                "installed": det.installed,
                "version": det.version,
                "transport": det.transport,
                "automatable": det.automatable,
                "detail": det.detail,
                "usable_capabilities": sorted(
                    k.value for k, v in caps.items() if v.usable),
                "blocked_capabilities": {
                    k.value: v.status.value
                    for k, v in caps.items() if not v.usable},
            }
        return out

    # ------------------------------------------------------------------
    # Matrice de routes
    # ------------------------------------------------------------------
    def _pair_feasible(self, src: AutodeskConnector,
                       dst: AutodeskConnector) -> Tuple[bool, List[str]]:
        """
        Une route A->B est possible si A PEUT lire (-> pivot) et B PEUT
        écrire (<- pivot). Les capacités NON utilisables bloquent avec motif.
        """
        missing: List[str] = []
        if not src.can(Capability.READ_MODEL):
            st = src.status_of(Capability.READ_MODEL)
            missing.append(f"{src.name}.read_model={st.value}")
        if not dst.can(Capability.WRITE_MODEL):
            st = dst.status_of(Capability.WRITE_MODEL)
            missing.append(f"{dst.name}.write_model={st.value}")
        return (not missing, missing)

    def routes(self) -> Dict[str, Dict[str, dict]]:
        """
        Matrice N×N des routes : pour chaque paire (source, target), la
        faisabilité + le motif si non faisable. La réciprocité est donc
        EXPLICITE dans la matrice (A->B et B->A évaluées séparément).
        """
        matrix: Dict[str, Dict[str, dict]] = {}
        for sname, src in self._connectors.items():
            matrix[sname] = {}
            for tname, dst in self._connectors.items():
                if sname == tname:
                    matrix[sname][tname] = {
                        "feasible": False,
                        "reason": "même logiciel (route inutile)",
                        "missing": []}
                    continue
                ok, missing = self._pair_feasible(src, dst)
                matrix[sname][tname] = {
                    "feasible": ok,
                    "reason": "A -> pivot -> B" if ok else
                              "capacité manquante",
                    "missing": missing,
                }
        return matrix

    def routes_flat(self) -> List[dict]:
        """Version liste (affichage GUI / tableau)."""
        out: List[dict] = []
        for s, row in self.routes().items():
            for t, info in row.items():
                out.append({"source": s, "target": t, **info})
        return out

    def reciprocal_pairs(self) -> List[Tuple[str, str]]:
        """
        Paires connectées DANS LES DEUX SENS (le cœur de la demande).
        Une paire n'apparaît que si A->B ET B->A sont faisables.
        """
        m = self.routes()
        out: List[Tuple[str, str]] = []
        seen = set()
        for s, row in m.items():
            for t, info in row.items():
                if s == t or not info["feasible"]:
                    continue
                if m.get(t, {}).get(s, {}).get("feasible"):
                    key = tuple(sorted((s, t)))
                    if key not in seen:
                        seen.add(key)
                        out.append(key)
        return sorted(out)

    def unavailability(self, source: str, target: str) -> RouteUnavailability:
        """Motif détaillé d'une route impossible (jamais un échec muet)."""
        m = self.routes()
        info = m.get(source, {}).get(target)
        if info is None:
            return RouteUnavailability(
                source, target, "connecteur(s) inconnu(s)",
                missing=[n for n in (source, target)
                         if n not in self._connectors])
        if info["feasible"]:
            return RouteUnavailability(source, target, "route faisable",
                                       missing=[])
        return RouteUnavailability(source, target, info["reason"],
                                   missing=list(info["missing"]))

    # ------------------------------------------------------------------
    # Échange réciproque : A -> pivot -> B
    # ------------------------------------------------------------------
    def exchange(self, source: str, target: str, project: Any,
                 connect: bool = True) -> ExchangeResult:
        """
        Exécute A -> pivot -> B.

        1. vérifie la faisabilité (sinon retourne success=False + motif) ;
        2. `source.read_model(project)` ;
        3. `target.write_model(project)`.

        Échec à l'une des étapes -> `success=False` + `step_failed`.
        """
        if source == target:
            return ExchangeResult(
                source, target, False, "read",
                message="Échange identique->identique refusé.")
        try:
            src = self.get(source)
            dst = self.get(target)
        except InteropError as exc:
            return ExchangeResult(source, target, False, "read",
                                  message=str(exc))

        ok, missing = self._pair_feasible(src, dst)
        if not ok:
            return ExchangeResult(
                source, target, False, "read",
                message="Route non faisable : " + ", ".join(missing))

        if connect:
            for conn in (src, dst):
                if not conn.connected:
                    try:
                        conn.connect()
                    except Exception:
                        pass  # l'opératrice suivante renverra REFUSED explicite

        # Étape 1 : logiciel -> pivot
        try:
            r_read = src.read_model(project)
        except Exception as exc:
            return ExchangeResult(
                source, target, False, "read",
                message=f"lecture {source} en échec : {exc}")
        if not r_read.ok:
            return ExchangeResult(
                source, target, False, "read", read_report=r_read,
                message=f"lecture {source} refusée/échouée "
                        f"({r_read.status}) : {r_read.message}")

        # Étape 2 : pivot -> logiciel
        try:
            r_write = dst.write_model(project)
        except Exception as exc:
            return ExchangeResult(
                source, target, False, "write", read_report=r_read,
                message=f"écriture {target} en échec : {exc}")
        if not r_write.ok:
            return ExchangeResult(
                source, target, False, "write",
                read_report=r_read, write_report=r_write,
                message=f"écriture {target} refusée/échouée "
                        f"({r_write.status}) : {r_write.message}")

        return ExchangeResult(
            source, target, True,
            read_report=r_read, write_report=r_write,
            pivot_stats=dict(r_write.objects),
            message=f"{source} -> pivot -> {target} : OK")

    # ------------------------------------------------------------------
    def disconnect_all(self) -> None:
        """Ferme toutes les sessions (sans sauvegarde, §5.4)."""
        for c in self._connectors.values():
            try:
                c.disconnect()
            except Exception:
                pass

    def summary(self) -> str:
        """Synthèse texte (dashboard GUI)."""
        st = self.status()
        lines = [f"Interop Autodesk — {len(st)} connecteur(s)"]
        for name, info in st.items():
            flag = "OK  " if info["automatable"] else "----"
            lines.append(
                f"  [{flag}] {name}: {info['label']}"
                f"{' ' + info['version'] if info['version'] else ''}"
                f" ({info['transport']}"
                f"{', installé' if info['installed'] else ', absent'})")
            if info["usable_capabilities"]:
                lines.append(
                    f"         utiles : "
                    f"{', '.join(info['usable_capabilities'])}")
            for cap, stt in info["blocked_capabilities"].items():
                if stt not in ("SUPPORTED", "PARTIAL"):
                    lines.append(f"         bloqué : {cap}={stt}")
        pairs = self.reciprocal_pairs()
        lines.append(f"  Paires RÉCIPROQUES : "
                     f"{', '.join(f'{a}<->{b}' for a, b in pairs) or 'aucune'}")
        return "\n".join(lines)
