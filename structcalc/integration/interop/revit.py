# -*- coding: utf-8 -*-
"""
integration/interop/revit.py — Adaptateur Revit dans l'architecture en étoile.

Vérité (Phase 0 audité, spec §6, §19) :
  - Revit 2027 installé, API .NET (RevitAPI.dll / RevitAPIUI.dll) présente.
  - AUCUN ProgID COM pour le modèle : l'accès profond passe par l'add-in
    .NET STRUCTCALC (Named Pipe \\\\.\\pipe\\structcalc_revit, NDJSON).
  - Les clés Registre `Revit.Family`, `Revit.Project`... sont des
    ASSOCIATIONS DE FICHIERS, pas de l'automatisation.

Connexion au modèle (état RÉEL, sondé à chaque fois, cache court) :
  - add-in chargé (PING/NDJSON vérifié) -> READ_MODEL / WRITE_MODEL
    utilisables (PARTIAL : sous-ensemble documenté, §19) ;
  - add-in absent -> capacités NON utilisables + motif d'action EXPLICITE
    (compiler/déployer l'add-in, ouvrir un document). Jamais de faux succès.

Le connecteur conserve le mappage SC-* <-> ElementId Revit issu de la
dernière lecture : toute écriture sans lecture préalable est refusée
(aucun identifiant n'est inventé).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ...core.model import (
    Beam, Column, CrossSection, ExternalRef, LoadCase, Material, Node, Support,
)
from ...core.status import DataStatus
from ...core.tracked import Provenance, TrackedValue
from ..interop.base import (
    AutodeskConnector, Capability, CapabilityReport, CapabilityStatus,
    Detection, InteropError, OpReport,
)


class RevitConnector(AutodeskConnector):
    """
    Pont Revit <-> pivot SC-* : détection réelle + add-in .NET sondé.

    Les capacités READ_MODEL / WRITE_MODEL reflètent l'état du Named Pipe
    (add-in chargé ou non) — le motif de refus est toujours actionable.
    """

    name = "revit"
    label = "Autodesk Revit"

    EXE_CANDIDATES = [
        r"C:\Program Files\Autodesk\Revit 2027\Revit.exe",
    ]
    # Clés de registre = associations de fichiers (PAS de l'automatisation)
    FILE_ASSOC_KEYS = ("Revit.Family", "Revit.Project", "Revit.Template")
    # API .NET réellement recherchée (présence = transport .NET, pas COM)
    DOTNET_DLLS = ("RevitAPI.dll", "RevitAPIUI.dll")
    #: Nom du pipe Named Pipe servi par l'add-in .NET
    DEFAULT_PIPE = "structcalc_revit"

    def __init__(self, exe_path: Optional[str] = None,
                 pipe_name: str = DEFAULT_PIPE, probe_ttl: float = 5.0):
        self.exe_path = exe_path or self._find_exe()
        self._process = None
        self.pipe_name = pipe_name
        #: Durée de validité de la sonde pipe (capacités appellées souvent)
        self.probe_ttl = probe_ttl
        self._probe_cache: Optional[Tuple[float, bool, str]] = None
        # Mappages issus de la dernière read_model réussie (SC-* <-> Revit)
        self._node_map: Dict[str, int] = {}       # SC-NODE-V* -> index DTO
        self._bar_map: Dict[str, int] = {}        # SC-BEAM/COLUMN-V* -> ElementId

    @classmethod
    def _find_exe(cls) -> Optional[str]:
        for p in cls.EXE_CANDIDATES:
            if os.path.isfile(p):
                return p
        return None

    # ------------------------------------------------------------------
    # Détection
    # ------------------------------------------------------------------
    def detect(self) -> Detection:
        installed = self.exe_path is not None
        version = ""
        if installed:
            folder = os.path.basename(os.path.dirname(self.exe_path))
            version = "".join(c for c in folder if c.isdigit()) or folder

        # ProgID COM modèle ? -> NON (les clés trouvées sont des assos fichiers)
        com_progids: List[str] = []
        try:
            import winreg
            for pid in ("Revit.Application", "Revit.Application.1"):
                try:
                    winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                   pid + r"\CLSID").Close()
                    com_progids.append(pid)
                except OSError:
                    continue
        except ImportError:  # pragma: no cover
            pass

        # Transport RÉEL du modèle : l'add-in .NET (pipe sondé), pas le COM
        alive, _ = self.probe_addin()
        if installed and alive:
            detail = (f"API .NET + add-in STRUCTCALC actif (pipe "
                      f"\\\\.\\pipe\\{self.pipe_name}) : modèle accessible.")
        elif installed:
            detail = ("API .NET uniquement : accès au modèle exige l'add-in "
                      "STRUCTCALC chargé (spec §6.3). Aucun COM modèle.")
        else:
            detail = "Revit introuvable dans les chemins candidats"

        return Detection(
            name=self.name, installed=installed, version=version,
            progs=com_progids,          # vide = aucun COM modèle
            transport="dotnet" if installed else "none",
            automatable=bool(installed and alive),  # pipe = transport réel
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Sonde de l'add-in (PING/NDJSON réel, cache TTL)
    # ------------------------------------------------------------------
    def probe_addin(self, force: bool = False) -> Tuple[bool, str]:
        """
        Vérifie QUELQUE CHOSE de réel : existence du pipe + PING/NDJSON.

        Retourne (alive, motif). Le motif est toujours actionnable.
        """
        now = time.monotonic()
        if (not force and self._probe_cache is not None
                and now - self._probe_cache[0] < self.probe_ttl):
            return self._probe_cache[1], self._probe_cache[2]

        alive, detail = self._probe_once()
        self._probe_cache = (now, alive, detail)
        return alive, detail

    def _probe_once(self) -> Tuple[bool, str]:
        from .revit_addin_client import RevitAddinClient

        absent = (
            f"add-in .NET STRUCTCALC non chargé : pipe "
            f"\\\\.\\pipe\\{self.pipe_name} introuvable. Actions : "
            "(1) compiler StructCalcAddin (dotnet build), "
            "(2) déployer via tools/deploy_revit_addin.py, "
            "(3) démarrer Revit 2027 avec un document ouvert.")
        try:
            client = RevitAddinClient(pipe_name=self.pipe_name)
        except RuntimeError as exc:          # pywin32 absent
            return False, f"{absent} (pywin32 absent : {exc})"
        try:
            # 3 tentatives : le serveur crée une nouvelle instance de pipe
            # entre deux clients (fenêtre de millisecondes) — 0,1 s chacune
            if not client.connect(retries=3, delay_s=0.1,
                                  retry_not_found=True):
                return False, absent
            if not client.ping():
                return False, (
                    f"pipe \\\\.\\pipe\\{self.pipe_name} présent mais PING "
                    f"invalide : add-in incompatible ou occupé — redémarrez "
                    f"Revit.")
            return True, (f"add-in .NET STRUCTCALC actif : PING/NDJSON "
                          f"vérifié sur \\\\.\\pipe\\{self.pipe_name}.")
        except Exception as exc:
            return False, (
                f"sonde du pipe en échec : {exc} — redémarrez Revit avec "
                f"l'add-in STRUCTCALC chargé.")
        finally:
            client.disconnect()

    # ------------------------------------------------------------------
    # Capacités (§19 : refus explicites, retournables selon l'état réel)
    # ------------------------------------------------------------------
    def _absent_motif(self) -> str:
        return self.probe_addin()[1]

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        det_installed = self.exe_path is not None
        if not det_installed:
            return {c: CapabilityReport(c, CapabilityStatus.NOT_IMPLEMENTED,
                                        "Revit non installé")
                    for c in Capability}

        alive, why = self.probe_addin()
        if alive:
            model_cap = CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.PARTIAL,
                "add-in .NET actif (PING vérifié) : lecture du modèle via "
                "pipe (nœuds, poteaux/poutres, sections, appuis ponctuels, "
                "cas de charge). Couverture partielle : charges d'éléments, "
                "appuis linéaires/aires et propriétés physiques des "
                "matériaux NON extraits (motifs dans les notes add-in).")
            write_cap = CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.PARTIAL,
                "add-in .NET actif (PING vérifié) : écriture des sections de "
                "barres via APPLY_CHANGES (transaction unique Revit). "
                "Couverture partielle : appuis non écrits (références "
                "d'hôte requises), armatures seulement barres droites à "
                "l'axe (enrobage non fourni = jamais inventé).")
            connect_detail = ("Ouverture processus d'un .rvt + session pipe "
                              "add-in vérifiée (PING).")
        else:
            model_cap = CapabilityReport(
                Capability.READ_MODEL, CapabilityStatus.NOT_SUPPORTED,
                "lecture REFUSÉE en l'état : " + why)
            write_cap = CapabilityReport(
                Capability.WRITE_MODEL, CapabilityStatus.NOT_SUPPORTED,
                "écriture REFUSÉE en l'état : " + why)
            connect_detail = ("Ouverture processus d'un .rvt uniquement — "
                              "session de modèle via add-in indisponible : "
                              + why)

        return {
            Capability.DETECT: CapabilityReport(
                Capability.DETECT, CapabilityStatus.SUPPORTED,
                "Chemin exe + absence COM modèle vérifiés (Phase 0)"),
            Capability.CONNECT: CapabilityReport(
                Capability.CONNECT, CapabilityStatus.PARTIAL, connect_detail),
            Capability.READ_MODEL: model_cap,
            Capability.WRITE_MODEL: write_cap,
            Capability.READ_RESULTS: CapabilityReport(
                Capability.READ_RESULTS, CapabilityStatus.NOT_SUPPORTED,
                "Revit n'expose pas de solveur : résultats via Robot/SMXX"),
            Capability.WRITE_LOADS: CapabilityReport(
                Capability.WRITE_LOADS, CapabilityStatus.NOT_SUPPORTED,
                "L'add-in n'implémente pas le transfert de charges "
                "(implémentés : READ_MODEL, APPLY_CHANGES, PING)"),
            Capability.READ_DRAWINGS: CapabilityReport(
                Capability.READ_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Pas d'accès aux vues/graphiques sans add-in dédié"),
            Capability.WRITE_DRAWINGS: CapabilityReport(
                Capability.WRITE_DRAWINGS, CapabilityStatus.NOT_SUPPORTED,
                "Idem"),
        }

    # ------------------------------------------------------------------
    # Session (processus, pas COM modèle)
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return (self._process is not None
                and self._process.poll() is None)

    def connect(self, timeout: float = 60.0) -> "RevitConnector":
        """
        Ouvre Revit (processus). NE fournit AUCUN accès au modèle.

        Une session "connectée" Revit ici signifie seulement que le
        processus tourne — le modèle est accessible via l'add-in .NET
        (sondé par probe_addin), jamais via COM.
        """
        if not self.exe_path:
            raise InteropError(
                "[revit] Revit introuvable : spécifiez exe_path ou "
                "installez Revit (§19, aucun lancement simulé).")
        return self

    def launch_file(self, rvt_path: str) -> int:
        """Ouvre un .rvt dans Revit (processus). Lève si fichier absent."""
        import subprocess
        if not self.exe_path:
            raise InteropError("[revit] Revit introuvable.")
        rvt_path = os.path.abspath(rvt_path)
        if not os.path.isfile(rvt_path):
            raise InteropError(f"[revit] Fichier RVT introuvable : {rvt_path}")
        self._process = subprocess.Popen([self.exe_path, rvt_path])
        return self._process.pid

    def disconnect(self) -> None:
        """Ferme le processus Revit SI on l'a lancé nous-mêmes."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None

    # ------------------------------------------------------------------
    # Ponts vers/depuis le pivot (§19 : aucun faux succès)
    # ------------------------------------------------------------------
    def read_model(self, project: Any) -> OpReport:
        if not self.exe_path:
            return OpReport(
                "read_model", "NOT_IMPLEMENTED", source=self.name,
                message=("[revit] lecture du modèle BIM REFUSÉE : Revit non "
                         "installé (§19). Aucun objet importé."))

        # Pivot obligatoire : viser le VRAI dict `nodes`/`beams`
        nodes = getattr(project, "nodes", None)
        beams = getattr(project, "beams", None)
        if not isinstance(nodes, dict) or not isinstance(beams, dict):
            return OpReport(
                "read_model", "NOT_IMPLEMENTED", source=self.name,
                message=("[revit] lecture du modèle BIM REFUSÉE : pivot non "
                         "fourni ou sans conteneurs nodes/beams (dict) — "
                         "objet non exploitable. Aucun objet importé."))

        alive, why = self.probe_addin()
        if not alive:
            return OpReport(
                "read_model", "NOT_IMPLEMENTED", source=self.name,
                message=f"[revit] lecture du modèle BIM REFUSÉE : {why} "
                        f"Aucun objet importé.")

        # -- Échange réel via le pipe --
        from .revit_addin_client import RevitAddinClient
        try:
            client = RevitAddinClient(pipe_name=self.pipe_name,
                                      timeout_ms=30000)
        except RuntimeError as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"[revit] client pipe indisponible : {exc}")
        if not client.connect(retries=3, delay_s=0.2):
            return OpReport(
                "read_model", "REFUSED", source=self.name,
                message=("[revit] pipe présent à la sonde mais connexion "
                         "impossible (occupé ou fermé entre-temps) — "
                         "réessayez. Aucun objet importé."))
        try:
            resp = client.read_model()
        except Exception as exc:
            return OpReport("read_model", "ERROR", source=self.name,
                            message=f"[revit] échange pipe échoué : {exc}")
        finally:
            client.disconnect()

        if not resp.success:
            return OpReport(
                "read_model", "REFUSED", source=self.name,
                message=("[revit] lecture REFUSÉE par l'add-in Revit : "
                         + (resp.error or "raison inconnue (enveloppe "
                            "incomplète)")))
        data = resp.data
        if not isinstance(data, dict):
            return OpReport(
                "read_model", "ERROR", source=self.name,
                message=("[revit] payload READ_MODEL illisible (objet attendu) "
                         "— rien importé (aucune donnée devinée)."))

        return self._import_model(project, data)

    def _import_model(self, project: Any, data: dict) -> OpReport:
        """Importe le DTO add-in dans le pivot (unités : m -> cm pivot)."""
        prov = Provenance.imported_from("Revit", version=self.detect().version)
        counts = {"nodes": 0, "columns": 0, "beams": 0, "sections": 0,
                  "materials": 0, "supports": 0, "load_cases": 0,
                  "duplicates": 0, "unresolved": 0}

        columns = getattr(project, "columns", None)
        beams = getattr(project, "beams", None)
        sections = getattr(project, "sections", None)
        materials = getattr(project, "materials", None)
        supports = getattr(project, "supports", None)
        load_cases = getattr(project, "load_cases", None)
        if not all(isinstance(d, dict) for d in
                   (project.nodes, project.beams, columns, sections,
                    materials, supports, load_cases)):
            return OpReport(
                "read_model", "REFUSED", source=self.name,
                message=("[revit] pivot incomplet (conteneurs manquants) — "
                         "import impossible sans inventaire."))

        self._node_map.clear()
        self._bar_map.clear()
        section_by_name: Dict[str, str] = {}
        material_by_key: Dict[Tuple[str, str], str] = {}

        # ---- Nœuds (+ appuis) ----
        for rn in data.get("nodes") or ():
            if not isinstance(rn, dict):
                continue
            idx = int(rn.get("id") or 0)
            sc = f"SC-NODE-V{idx:06d}"
            self._node_map[sc] = idx
            if sc in project.nodes:
                counts["duplicates"] += 1
                continue
            pos = rn.get("position") or {}
            node = Node(
                sc_id=sc, name=str(rn.get("name") or sc),
                x=_tv_len(pos.get("x"), prov),
                y=_tv_len(pos.get("y"), prov),
                z=_tv_len(pos.get("z"), prov),
            )
            sup_sc = self._import_support(rn, sc, prov, supports, counts)
            if sup_sc is not None:
                node.support = supports[sup_sc]
            project.nodes[sc] = node
            counts["nodes"] += 1

        # ---- Sections (une par nom, converties m -> cm/cm²/cm⁴) ----
        for rb in data.get("bars") or ():
            if not isinstance(rb, dict):
                continue
            sec_dto = rb.get("section")
            if not isinstance(sec_dto, dict):
                continue
            sname = str(sec_dto.get("name") or "")
            if not sname or sname in section_by_name:
                continue
            sc = f"SC-SECTION-V{len(section_by_name) + 1:06d}"
            kind = str(sec_dto.get("shape") or "").lower()  # rect/circ ou ""
            sec = CrossSection(sc_id=sc, name=sname, kind=kind)
            b_m = sec_dto.get("width")
            h_m = sec_dto.get("height")
            dia_m = sec_dto.get("diameter")
            if dia_m is not None:
                # circulaire : b = h = diamètre (pivot sans champ dédié)
                sec.b = _tv_len(dia_m * 100.0, prov, unit="cm")
                sec.h = _tv_len(dia_m * 100.0, prov, unit="cm")
            else:
                # m (Revit) -> cm (pivot) : ×100 sur les dimensions
                sec.b = _tv_len(b_m * 100.0 if b_m is not None else None,
                                prov, unit="cm")
                sec.h = _tv_len(h_m * 100.0 if h_m is not None else None,
                                prov, unit="cm")
            if sec_dto.get("area") is not None:
                sec.area = TrackedValue.of(
                    float(sec_dto["area"]) * 1e4, "cm2",
                    DataStatus.IMPORTED, prov)     # m² -> cm²
            if sec_dto.get("iy") is not None:
                sec.Iy = TrackedValue.of(
                    float(sec_dto["iy"]) * 1e8, "cm4",
                    DataStatus.IMPORTED, prov)     # m⁴ -> cm⁴
            if sec_dto.get("iz") is not None:
                sec.Iz = TrackedValue.of(
                    float(sec_dto["iz"]) * 1e8, "cm4",
                    DataStatus.IMPORTED, prov)
            sections[sc] = sec
            section_by_name[sname] = sc
            counts["sections"] += 1

        # ---- Matériaux (physique Revit non lisible : reste MISSING) ----
        for rb in data.get("bars") or ():
            if not isinstance(rb, dict):
                continue
            mat_dto = rb.get("material")
            if not isinstance(mat_dto, dict):
                continue
            mname = str(mat_dto.get("name") or "")
            mtype = str(mat_dto.get("type") or "")
            key = (mname, mtype)
            if not mname or key in material_by_key:
                continue
            sc = f"SC-MATERIAL-V{len(material_by_key) + 1:06d}"
            kind = _material_kind(mtype)
            mat = Material(sc_id=sc, name=mname, kind=kind)
            # Fc/Fy/E (Pa add-in -> MPa pivot) : seulement si RÉELLEMENT présents
            if mat_dto.get("fc") is not None:
                mat.fck = TrackedValue.of(float(mat_dto["fc"]) / 1e6, "MPa",
                                          DataStatus.IMPORTED, prov)
            if mat_dto.get("fy") is not None:
                mat.fyd = TrackedValue.of(float(mat_dto["fy"]) / 1e6, "MPa",
                                          DataStatus.IMPORTED, prov)
            if mat_dto.get("e") is not None:
                mat.E = TrackedValue.of(float(mat_dto["e"]) / 1e6, "MPa",
                                        DataStatus.IMPORTED, prov)
            materials[sc] = mat
            material_by_key[key] = sc
            counts["materials"] += 1

        # ---- Cas de charge ----
        for k, lc_dto in enumerate(data.get("loadCases") or (), start=1):
            if not isinstance(lc_dto, dict):
                continue
            num = lc_dto.get("number")
            sc = f"SC-LCASE-V{(int(num) if num is not None else k):06d}"
            if sc in load_cases:
                counts["duplicates"] += 1
                continue
            nature = str(lc_dto.get("type") or "")
            load_cases[sc] = LoadCase(
                sc_id=sc, name=str(lc_dto.get("name") or sc),
                kind=nature.lower(), nature=nature)
            counts["load_cases"] += 1

        # ---- Barres : poteaux et poutres distingués (structuralType) ----
        for rb in data.get("bars") or ():
            if not isinstance(rb, dict):
                continue
            elem = int(rb.get("id") or 0)
            s_sc = self._node_sc(rb.get("startNodeId"))
            e_sc = self._node_sc(rb.get("endNodeId"))
            if s_sc is None or e_sc is None:
                counts["unresolved"] += 1     # jamais de nœud inventé
                continue
            is_column = str(rb.get("structuralType") or "") == "Column"
            sc = f"SC-{'COLUMN' if is_column else 'BEAM'}-V{elem:06d}"
            container = columns if is_column else beams
            self._bar_map[sc] = elem
            if sc in container:
                counts["duplicates"] += 1
                continue
            name = str(rb.get("name") or sc)
            sec_sc = section_by_name.get(
                str((rb.get("section") or {}).get("name") or ""))
            mat_sc = material_by_key.get(
                (str((rb.get("material") or {}).get("name") or ""),
                 str((rb.get("material") or {}).get("type") or "")))
            span = self._span_between(project, s_sc, e_sc, prov)
            if is_column:
                member = Column(sc_id=sc, name=name, start_node=s_sc,
                                end_node=e_sc, section=sec_sc,
                                material=mat_sc, height=span)
            else:
                member = Beam(sc_id=sc, name=name, start_node=s_sc,
                              end_node=e_sc, section=sec_sc,
                              material=mat_sc, span=span)
            member.add_external_ref(ExternalRef(
                software="Revit", version=self.detect().version,
                external_id=str(elem), match_status="MATCHED"))
            container[sc] = member
            counts["beams" if not is_column else "columns"] += 1

        addin_notes = [str(n) for n in (data.get("notes") or ())
                       if isinstance(n, str)]
        gaps = counts["unresolved"]
        status = "OK" if not gaps else "PARTIAL"
        msg = "modèle Revit importé via add-in .NET (pipe structcalc_revit)"
        if gaps:
            msg += (f" ; {gaps} barre(s) avec extrémité(s) non résolvable(s) "
                    f"— ignorée(s) sans invention")
        if addin_notes:
            preview = " | ".join(addin_notes[:3])
            msg += f" ; périmètre add-in : {preview}"
        return OpReport("read_model", status, source=self.name,
                        target=getattr(project, "sc_id", ""),
                        objects=counts, message=msg)

    def write_model(self, project: Any) -> OpReport:
        if not self.exe_path:
            return OpReport(
                "write_model", "NOT_IMPLEMENTED", source=self.name,
                message=("[revit] écriture du modèle BIM REFUSÉE : Revit non "
                         "installé (§19). Aucun objet écrit."))

        alive, why = self.probe_addin()
        if not alive:
            return OpReport(
                "write_model", "NOT_IMPLEMENTED", source=self.name,
                message=f"[revit] écriture du modèle BIM REFUSÉE : {why} "
                        f"Aucun objet écrit.")

        if not self._bar_map:
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[revit] écriture REFUSÉE : aucune correspondance "
                         "SC-* <-> ElementId connue — lisez d'abord le "
                         "modèle Revit (read_model). Aucun identifiant "
                         "inventé, aucun objet écrit."))

        beams = getattr(project, "beams", None)
        columns = getattr(project, "columns", None)
        sections = getattr(project, "sections", None)
        if not all(isinstance(d, dict) for d in (beams, columns, sections)):
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[revit] écriture REFUSÉE : pivot incomplet "
                         "(beams/columns/sections manquants)."))

        # -- Construction des changements (sections définies uniquement) --
        bar_changes: List[dict] = []
        skipped = 0
        for sc, elem in self._bar_map.items():
            member = beams.get(sc) or columns.get(sc)
            if member is None:
                continue
            sec = (sections.get(member.section)
                   if getattr(member, "section", None) else None)
            if sec is None or not sec.is_defined():
                skipped += 1        # section non définie : jamais devinée
                continue
            b_cm = float(sec.b.value)
            h_cm = float(sec.h.value)
            sec_name = sec.name or f"SC {round(b_cm)}x{round(h_cm)}"
            if "circular" in (sec.kind or "").lower():
                payload_sec = {"diameter": b_cm / 100.0}
            else:
                payload_sec = {"width": b_cm / 100.0, "height": h_cm / 100.0}
            bar_changes.append({
                "elementId": elem,
                "newSectionName": sec_name,
                "newSection": payload_sec,
            })

        if not bar_changes:
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                objects={"skipped": skipped},
                message=("[revit] écriture REFUSÉE : aucune section définie "
                         "dans le pivot pour les barres importées — "
                         f"{skipped} barre(s) sans section (données "
                         f"manquantes, jamais inventées)."))

        from .revit_addin_client import RevitAddinClient
        try:
            client = RevitAddinClient(pipe_name=self.pipe_name,
                                      timeout_ms=30000)
        except RuntimeError as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"[revit] client pipe indisponible : {exc}")
        if not client.connect(retries=3, delay_s=0.2):
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[revit] pipe présent à la sonde mais connexion "
                         "impossible (occupé ou fermé entre-temps) — "
                         "réessayez. Aucun objet écrit."))
        try:
            resp = client.apply_changes(
                {"barChanges": bar_changes, "nodeChanges": []})
        except Exception as exc:
            return OpReport("write_model", "ERROR", source=self.name,
                            message=f"[revit] échange pipe échoué : {exc}")
        finally:
            client.disconnect()

        if not resp.success:
            return OpReport(
                "write_model", "REFUSED", source=self.name,
                message=("[revit] écriture REFUSÉE par l'add-in Revit : "
                         + (resp.error or "raison inconnue")))

        result = resp.data if isinstance(resp.data, dict) else {}
        addin_notes = [str(n) for n in (result.get("notes") or ())
                       if isinstance(n, str)]
        objects = {
            "bars_sent": len(bar_changes),
            "bars_updated": int(result.get("barsUpdated") or 0),
            "rebars_created": int(result.get("rebarsCreated") or 0),
            "skipped": skipped,
        }
        msg = (f"{objects['bars_updated']} barre(s) mise(s) à jour via "
               f"add-in Revit ; {skipped} sans section définie (ignorée(s))")
        if addin_notes:
            msg += " ; " + " | ".join(addin_notes[:3])
        return OpReport("write_model", "OK", source=self.name,
                        target=getattr(project, "sc_id", ""),
                        objects=objects, message=msg)

    # ------------------------------------------------------------------
    # Helpers d'import
    # ------------------------------------------------------------------
    def _node_sc(self, dto_id: Any) -> Optional[str]:
        if dto_id is None:
            return None
        sc = f"SC-NODE-V{int(dto_id):06d}"
        return sc if sc in self._node_map else None

    def _import_support(self, rn: dict, node_sc: str, prov, supports: dict,
                        counts: dict) -> Optional[str]:
        """Appui ponctuel -> Support (fixités réelles ou MISSING)."""
        if not rn.get("isSupport"):
            return None
        sc = node_sc.replace("SC-NODE-", "SC-SUPPORT-")   # SC-SUPPORT-V000001
        counts["supports"] += 1
        if sc in supports:
            return sc
        sup_dto = rn.get("support") if isinstance(rn.get("support"), dict) \
            else {}
        kind = str(sup_dto.get("preset") or "").lower()

        def fix(key: str) -> TrackedValue:
            v = sup_dto.get(key)
            if v is None:
                return TrackedValue.missing("-")   # indéterminable -> MISSING
            return TrackedValue.of(1.0 if v else 0.0, "-",
                                   DataStatus.IMPORTED, prov)

        supports[sc] = Support(
            sc_id=sc, name=f"Appui {node_sc}", kind=kind,
            dx=fix("fixedX"), dy=fix("fixedY"), dz=fix("fixedZ"),
            rx=fix("fixedRx"), ry=fix("fixedRy"), rz=fix("fixedRz"))
        return sc

    def _span_between(self, project: Any, s_sc: str, e_sc: str, prov) -> TrackedValue:
        """Distance entre deux nœuds importés (CALCULÉE, jamais devinée)."""
        ns = project.nodes.get(s_sc)
        ne = project.nodes.get(e_sc)
        cs = ns.coordinates() if ns else None
        ce = ne.coordinates() if ne else None
        if cs is None or ce is None:
            return TrackedValue.missing("m")
        d2 = sum((a - b) ** 2 for a, b in zip(cs, ce))
        return TrackedValue.of(d2 ** 0.5, "m", DataStatus.CALCULATED,
                               Provenance.calculated_by(
                                   "distance des nœuds importés (Revit)"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tv_len(value: Any, prov, unit: str = "m") -> TrackedValue:
    if value is None:
        return TrackedValue.missing(unit)
    return TrackedValue.of(float(value), unit, DataStatus.IMPORTED, prov)


def _material_kind(revit_type: str) -> str:
    t = (revit_type or "").lower()
    if "concrete" in t or "béton" in t or "precast" in t:
        return "concrete"
    if "steel" in t or "acier" in t or "aluminum" in t or "aluminium" in t:
        return "steel" if "steel" in t or "acier" in t else "aluminum"
    if "wood" in t or "bois" in t:
        return "wood"
    return t or "unknown"
