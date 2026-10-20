# -*- coding: utf-8 -*-
"""
integration/robot/connection.py — Connexion à Autodesk Robot Structural Analysis.

Vérifié en Phase 0 sur Robot 2027 (voir docs/phase0/AUDIT_PHASE0.md) :
  - ProgID COM   : "Robot.Application"
  - Version      : 40.0.0.12707  (app.ProgramVersion)
  - TypeLib      : Exe\\robotom.tlb  (via comtypes si binding typé souhaité)
  - Ouverture    : Project.New(type)  ex. New(1) = I_PT_FRAME_2D
  - Accès modèle : Project.Structure  (PAS Project.Model)
  - Comptage     : serveur.GetAll().Count   (PAS serveur.Count)
  - Accès unitaire : serveur.Get(id)        (PAS serveur.Item(id))
  - Fermeture    : Project.Close()  sans argument

Ce module encapsule le cycle de vie : détection, connexion, ouverture de
projet, fermeture contrôlée. Aucun calcul métier ici (couche SOLVER ailleurs).
"""

from __future__ import annotations

import atexit
import os
import time
from typing import Optional

# Valeurs d'enum RobotOM vérifiées par sondage (IRobotProjectType)
PROJECT_TYPE_FRAME_2D = 1   # I_PT_FRAME_2D
PROJECT_TYPE_TRUSS_2D = 2   # I_PT_TRUSS_2D
PROJECT_TYPE_FRAME_3D = 4   # I_PT_FRAME_3D


class RobotConnectionError(Exception):
    """Erreur levée quand la connexion ou l'ouverture de projet échoue."""


def _robot_process_running() -> bool:
    """True si un robot.exe tourne déjà (tasklist — sans COM)."""
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq robot.exe", "/NH"],
            capture_output=True, text=True, timeout=15)
        return "robot.exe" in (out.stdout or "").lower()
    except Exception:
        return False


_TYPED_BINDING: Optional[bool] = None


def _ensure_typed_binding() -> bool:
    """
    Binding typé RobotOM (makepy) — best-effort, une fois par processus.

    Le dispatch DYNAMIQUE ne sait PAS lire les collections Robot : leur
    membre « Get » est une propriété indexée (dynamic renvoie un
    sous-objet COM au lieu d'un numéro — constaté en live le 19/10 sur la
    villa, dont la numérotation NON DENSE rendait le supposé 1..N fatal :
    Get(1) = nœud inexistant → E_UNEXPECTED alors que GetAll().Count
    répondait). Le binding typé, généré depuis le FICHIER robotom.tlb
    (le registre TypeLib est incomplet : TYPE_E_TYPELIB_NOT_REGISTERED),
    renvoie directement les objets IRobotNode/IRobotBar — import villa
    66 nœuds + 108 barres VÉRIFIÉ en live (1,3 s).
    En cas d'échec : dispatch dynamique conservé (repli historique).
    """
    global _TYPED_BINDING
    if _TYPED_BINDING is not None:
        return _TYPED_BINDING
    try:
        import pythoncom
        import win32com.client.makepy
        exe = RobotConnection._exe_path()
        base = (os.path.dirname(exe) if exe else
                r"C:\Program Files\Autodesk"
                r"\Robot Structural Analysis Professional 2027\Exe")
        tlb = os.path.join(base, "robotom.tlb")
        if not os.path.isfile(tlb):
            _TYPED_BINDING = False
            return False
        lib = pythoncom.LoadTypeLib(tlb)
        win32com.client.makepy.GenerateFromTypeLibSpec(lib)
        _TYPED_BINDING = True
    except Exception:
        _TYPED_BINDING = False
    return _TYPED_BINDING


class RobotConnection:
    """
    Connexion à une instance Robot Structural Analysis.

    Gère le cycle de vie COM et l'ouverture/fermeture de projet en toute
    sécurité (fermeture sans sauvegarde par défaut).

    Usage :
        with RobotConnection() as rc:
            S = rc.structure          # serveur de modèle
            ...

    Sécurité (spec §5.4) : la fermeture ne sauvegarde JAMAIS par défaut.
    """

    def __init__(self, visible: bool = True, attach_only: bool = False):
        self.visible = visible
        self.attach_only = attach_only
        self._app = None
        self._project = None
        self._opened_project = False
        self._connected = False

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------
    @staticmethod
    def _exe_path() -> str:
        """
        Chemin de robot.exe (registre LocalServer32), arguments retirés.

        Permet de LANCER Robot directement (processus VISIBLE, comme un
        double-clic) au lieu de l'activer via COM/SCM — l'activation SCM
        échoue au démarrage de la machine (constaté live : Robot reste des
        minutes derrière son premier écran avant de s'enregistrer, d'où
        CO_E_SERVER_EXEC_FAILURE).
        """
        try:
            import winreg
        except ImportError:          # pragma: no cover — non-Windows
            return ""
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                r"Robot.Application\CLSID") as k:
                clsid = winreg.QueryValueEx(k, "")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                rf"CLSID\{clsid}\LocalServer32") as k2:
                raw = str(winreg.QueryValueEx(k2, "")[0])
        except OSError:
            return ""
        raw = raw.strip().strip('"')
        exe = raw.split(" /")[0].split(" -")[0].strip().strip('"')
        return exe if os.path.isfile(exe) else ""

    def connect(self, timeout: float = 180.0) -> "RobotConnection":
        """
        Établit la connexion COM vers Robot.

        Ordre (constaté et VÉRIFIÉ en live) :
          1. GetActiveObject (instance déjà enregistrée COM) ;
          2. sinon, si robot.exe ne tourne PAS : lancer robot.exe
             DIRECTEMENT (processus VISIBLE, sans activation SCM — au
             démarrage de la machine l'activation SCM expire avant que
             Robot finisse son écran de démarrage : CO_E_SERVER_EXEC_
             FAILURE, constaté en live) ;
          3. Dispatch : s'attache à l'instance en cours (Robot est
             single-instance : Dispatch y redirige — VÉRIFIÉ live : Dispatch
             OK sur robot.exe déjà ouvert, AUCUNE seconde fenêtre) ; si
             rien ne tourne, il lance une instance via SCM (dernier recours).
        """
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        _ensure_typed_binding()   # collections Robot lisibles (typé)

        # 1) Instance existante
        try:
            self._app = win32com.client.GetActiveObject("Robot.Application")
        except Exception:
            self._app = None

        if self._app is None and self.attach_only:
            # Robot lance normalement (processus visible) n'est PAS dans le
            # ROT : seul Dispatch y attache (single-instance, VÉRIFIÉ live
            # sans seconde fenêtre). On l'autorise SI un robot.exe tourne
            # déjà — sinon on refuse (attach_only = ne jamais rien lancer).
            # Retry court : une instance fraîchement lancée peut ne pas avoir
            # encore enregistré son COM (constaté live).
            if _robot_process_running():
                deadline = time.monotonic() + 30.0
                while time.monotonic() < deadline and self._app is None:
                    try:
                        self._app = win32com.client.Dispatch("Robot.Application")
                    except Exception:
                        self._app = None
                        time.sleep(2.0)
            if self._app is None:
                raise RobotConnectionError(
                    "Aucune instance Robot active et attach_only=True."
                )

        if self._app is None:
            launched = False
            exe = ""
            if not _robot_process_running():
                # 2) Lancement direct VISIBLE (pas d'activation SCM)
                exe = self._exe_path()
                if exe:
                    try:
                        import subprocess
                        subprocess.Popen([exe])     # fenêtre Robot visible
                        launched = True
                    except Exception:
                        launched = False
            # 3) Dispatch avec ATTENTE + RETRY : une instance directement
            #    lancée met plusieurs dizaines de secondes à enregistrer son
            #    COM (constaté live : Dispatch immédiat ->
            #    CO_E_SERVER_EXEC_FAILURE). On réessaie jusqu'au timeout.
            deadline = time.monotonic() + (max(timeout, 30.0) if launched
                                           else 20.0)
            last: Optional[Exception] = None
            while time.monotonic() < deadline:
                try:
                    self._app = win32com.client.Dispatch("Robot.Application")
                    last = None
                    break
                except Exception as exc:
                    last = exc
                    if not launched and not _robot_process_running():
                        break        # rien à attendre : plus de processus
                    time.sleep(2.0)
            if self._app is None:
                hint = (f"Robot démarré ({exe}) mais l'attachement COM a "
                        f"échoué après {int(deadline)} s d'attente" if launched
                        else "Impossible de lancer Robot via COM")
                raise RobotConnectionError(
                    f"{hint} : {last} — ouvrez Robot manuellement puis "
                    "relancez (l'instance ouverte sera réutilisée)."
                ) from last

        self._connected = True
        atexit.register(self._emergency_close)
        return self

    @property
    def app(self):
        """Objet COM RobotApplication."""
        if not self._connected or self._app is None:
            raise RobotConnectionError("Non connecté. Appelez connect().")
        return self._app

    @property
    def project(self):
        """Objet COM IRobotProject (après new_project)."""
        if self._project is None:
            raise RobotConnectionError(
                "Aucun projet ouvert. Appelez new_project() ou open_project()."
            )
        return self._project

    @property
    def structure(self):
        """Serveur de modèle Project.Structure (le vrai accès, vérifié)."""
        return self.project.Structure

    @property
    def is_project_open(self) -> bool:
        """
        True si un projet est ouvert dans Robot.

        Session courante d'abord ; SINON on interroge l'application elle-même
        (app.Project.IsActive — membres vérifiés Phase 0) pour détecter un
        projet ouvert par une AUTRE session (reprise après erreur, ou travail
        utilisateur). Indispensable avant toute écriture (§5.4).
        """
        if self._project is not None:
            try:
                return bool(self._project.IsActive)
            except Exception:
                return False
        if self._app is None:
            return False
        try:
            return bool(self._app.Project.IsActive)
        except Exception:
            return False

    @property
    def opened_by_us(self) -> bool:
        """True si CETTE session a ouvert/créé le projet courant."""
        return bool(self._opened_project)

    def adopt_live_project(self) -> bool:
        """
        Adapte le projet OUVERT dans l'application par une autre session
        (votre travail dans Robot) pour la LECTURE seule.

        §5.4 : `opened_by_us` reste FAUX — toute écriture dans ce projet
        reste REFUSÉE avec son motif (aucune modification silencieuse du
        travail utilisateur). Renvoie False si aucun projet live n'est ouvert.
        """
        if self._project is not None:
            try:
                return bool(self._project.IsActive)
            except Exception:
                return False
        if self._app is None:
            return False
        try:
            proj = self._app.Project
            if proj is not None and proj.IsActive:
                self._project = proj
                self._opened_project = False   # JAMAIS notre ouvrage
                return True
        except Exception:
            return False
        return False

    # ------------------------------------------------------------------
    # Ouverture de projet
    # ------------------------------------------------------------------
    def new_project(self, project_type: int = PROJECT_TYPE_FRAME_2D) -> object:
        """
        Ouvre un nouveau projet vierge.

        project_type : IRobotProjectType
            1 = FRAME_2D (défaut), 2 = TRUSS_2D, 4 = FRAME_3D
        """
        proj = self.app.Project
        try:
            proj.New(int(project_type))
        except Exception as exc:
            raise RobotConnectionError(
                f"Project.New({project_type}) échoué : {exc}"
            ) from exc

        if not proj.IsActive:
            raise RobotConnectionError(
                "Project.New() n'a pas ouvert de projet (IsActive faux)."
            )
        self._project = proj
        self._opened_project = True
        return proj

    def open_project(self, rtd_path: str) -> object:
        """
        Ouvre un projet Robot existant (.rtd).

        NOTE : chemin non testé en Phase 0. À valider en Phase 2 (spec §17.3).
        """
        proj = self.app.Project
        try:
            proj.Open(rtd_path)
        except Exception as exc:
            raise RobotConnectionError(
                f"Project.Open('{rtd_path}') échoué : {exc}"
            ) from exc
        self._project = proj
        self._opened_project = True
        return proj

    # ------------------------------------------------------------------
    # Fermeture contrôlée
    # ------------------------------------------------------------------
    def close_project(self, save: bool = False) -> None:
        """
        Ferme le projet courant. Ne sauvegarde QUE si save=True (défaut False).

        Règle spec §5.4 : aucune modification silencieuse du modèle de
        production. La fermeture sans sauvegarde est le comportement sûr.
        """
        if self._project is None:
            return
        try:
            if save:
                self._project.Save()
            self._project.Close()
        except Exception as exc:
            raise RobotConnectionError(
                f"Fermeture du projet échouée : {exc}"
            ) from exc
        finally:
            self._project = None
            self._opened_project = False

    def disconnect(self, quit_app: Optional[bool] = None) -> None:
        """
        Ferme la connexion COM.

        quit_app=None : quitte Robot uniquement si nous l'avons lancé.
        quit_app=True : quitte toujours.
        quit_app=False : laisse Robot ouvert, on décroche.
        """
        if not self._connected:
            return
        # Fermer le projet ouvert sans sauvegarde si on l'a créé
        if self._project is not None and self._opened_project:
            try:
                self._project.Close()
            except Exception:
                pass
            self._project = None

        if quit_app:
            try:
                self._app.Quit()
            except Exception:
                pass
        self._app = None
        self._connected = False
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def _emergency_close(self) -> None:
        """Fermeture de sécurité à la sortie du processus Python."""
        try:
            if self._connected and self._project is not None and self._opened_project:
                self._project.Close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        # Fermeture sans sauvegarde : comportement sûr par défaut
        self.disconnect(quit_app=False)
        return False

    # ------------------------------------------------------------------
    # Informations
    # ------------------------------------------------------------------
    def info(self) -> dict:
        """Snapshot de l'état de la connexion (pour la GUI / journaux)."""
        out = {
            "connecté": self._connected,
            "projet_ouvert": self.is_project_open,
        }
        if self._connected:
            try:
                out["version"] = str(self._app.ProgramVersion)
            except Exception:
                out["version"] = "?"
        return out
