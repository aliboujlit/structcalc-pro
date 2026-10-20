# -*- coding: utf-8 -*-
"""
integration/interop/revit_addin_client.py — Client Python pour l'add-in
Revit STRUCTCALC PRO (Named Pipe, Windows).

Protocole (contrat BYTE-MODE, aligné sur l'add-in .NET) :
  - transport  : pipe nommé \\\\.\\pipe\\<nom>, **PipeTransmissionMode.Byte**
                 (aucun SetNamedPipeHandleState PIPE_READMODE_MESSAGE,
                 aucun FILE_FLAG_OVERLAPPED : en mode message, les trames
                 > 64 Ko sont tronquées et le BOM/splitting cassait le
                 parseur — corrigé) ;
  - trame      : une ligne JSON UTF-8 terminée par "\\n" (NDJSON) ;
  - enveloppe  : EXACTEMENT 4 clés côté add-in :
                 {"success": bool, "data": ..., "error": str,
                  "request_id": str}
                 La lecture est TOLÉRANTE : clés manquantes = défauts,
                 clés inconnues = ignorées (jamais d'exception sur forme).

Commandes : PING, READ_MODEL, APPLY_CHANGES, WRITE_MODEL.
(GET_ELEMENTS est refusé côté add-in avec motif explicite.)

Usage :
    client = RevitAddinClient()
    if client.connect():
        if client.ping():
            model = client.read_model()
        client.disconnect()

L'add-in doit être chargé dans Revit 2027
(fichier .addin dans %APPDATA%\\Autodesk\\Revit\\Addins\\2027\\).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

try:
    import win32file
    import win32pipe
    import pywintypes
except ImportError:  # pragma: no cover - environnement sans pywin32
    win32file = win32pipe = pywintypes = None

# Codes d'erreur Windows utiles
ERROR_FILE_NOT_FOUND = 2      # pipe absent (add-in non chargé)
ERROR_BROKEN_PIPE = 109       # serveur parti
ERROR_NO_DATA = 232           # serveur fermé côté lecture
ERROR_PIPE_BUSY = 231         # toutes les instances occupées
ERROR_MORE_DATA = 234         # trame plus grande que le buffer (mode message)


@dataclass
class PipeMessage:
    """Message NDJSON envoyé via le pipe."""
    command: str
    payload: str = ""
    request_id: str = ""


@dataclass
class ApiResponse:
    """
    Réponse standard de l'add-in (enveloppe à 4 clés).
    Construite de façon TOLÉRANTE : aucune clé n'est exigée pour
    instancier — success=False par défaut si la forme est inattendue.
    """
    success: bool = False
    data: Any = None
    error: str = ""
    request_id: str = ""

    @classmethod
    def from_dict(cls, raw: Any) -> "ApiResponse":
        if not isinstance(raw, dict):
            return cls(success=False,
                       error=f"réponse hors protocole (objet JSON attendu, "
                             f"reçu {type(raw).__name__})")
        return cls(
            success=bool(raw.get("success", False)),
            data=raw.get("data"),
            error=str(raw.get("error") or ""),
            request_id=str(raw.get("request_id") or ""),
        )


class RevitAddinClient:
    """
    Client pipe de l'add-in STRUCTCALC PRO Revit.

    Nécessite pywin32 (``pip install pywin32``) et l'add-in chargé.

    Note : ``timeout_ms`` plafonne les tentatives de CONNEXION ; une lecture
    en cours reste bloquante jusqu'à la réponse — l'add-in garantit une
    réponse (y compris une enveloppe d'erreur) avec un plafond interne de
    15 s par requête, ou la fermeture du pipe si Revit s'arrête.
    """

    def __init__(self, pipe_name: str = "structcalc_revit", timeout_ms: int = 5000):
        if win32pipe is None:
            raise RuntimeError("pywin32 requis : pip install pywin32")
        self.pipe_name = pipe_name
        self.timeout_ms = timeout_ms
        self._handle = None
        self._connected = False

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return bool(self._connected and self._handle)

    def connect(self, retries: int = 10, delay_s: float = 0.5,
                retry_not_found: bool = True) -> bool:
        """
        Se connecte au pipe nommé. Retourne False (sans lever) si absent.

        retry_not_found=False : l'absence (ERROR_FILE_NOT_FOUND) est
        définitive — utilisé par la sonde pour rester instantanée.
        """
        pipe_path = fr"\\.\pipe\{self.pipe_name}"
        for _ in range(max(1, retries)):
            try:
                # Mode OCTET : flags = 0 (FILE_FLAG_OVERLAPPED interdit un
                # ReadFile synchrone simple ; le mode message tronque >64 Ko)
                self._handle = win32file.CreateFile(
                    pipe_path,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None,
                    win32file.OPEN_EXISTING,
                    0, 0,
                )
                self._connected = True
                return True
            except pywintypes.error as e:
                code = getattr(e, "winerror", None)
                if code == ERROR_FILE_NOT_FOUND and not retry_not_found:
                    return False
                if code in (ERROR_FILE_NOT_FOUND, ERROR_BROKEN_PIPE,
                            ERROR_NO_DATA, ERROR_PIPE_BUSY):
                    time.sleep(delay_s)
                    continue
                raise
        return False

    def disconnect(self) -> None:
        if self._handle:
            try:
                win32file.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        self._connected = False

    # ------------------------------------------------------------------
    # Trames NDJSON (byte-mode)
    # ------------------------------------------------------------------
    def _send(self, msg: PipeMessage) -> None:
        if not self.connected:
            raise RuntimeError("Non connecté au pipe add-in Revit")
        data = (json.dumps(asdict(msg), ensure_ascii=False) + "\n").encode("utf-8")
        win32file.WriteFile(self._handle, data)

    def _recv(self) -> ApiResponse:
        """
        Lit une ligne NDJSON complète (accumulation jusqu'à '\\n').

        Gère ERROR_MORE_DATA (234) en boucle avec un tampon ≥ 1 Mo, puis
        parse de façon tolérante l'enveloppe à 4 clés.
        """
        if not self.connected:
            raise RuntimeError("Non connecté au pipe add-in Revit")

        buf = b""
        while b"\n" not in buf:
            try:
                hr, chunk = win32file.ReadFile(self._handle, 1 << 20)  # 1 Mo
            except pywintypes.error as e:
                code = getattr(e, "winerror", None)
                if code == ERROR_MORE_DATA:
                    # mode message : la trame continue (e.args[2] = fragment)
                    frag = e.args[2] if len(e.args) > 2 else b""
                    if isinstance(frag, str):
                        frag = frag.encode("utf-8")
                    buf += frag or b""
                    continue
                raise RuntimeError(
                    f"lecture du pipe interrompue (code {code}) : add-in ou "
                    f"Revit fermé pendant l'échange") from e

            if hr == ERROR_MORE_DATA:
                buf += chunk or b""
                continue
            if chunk:
                buf += chunk
            elif not chunk:
                # EOF sans saut de ligne : trame incomplète -> erreur honnête
                if not buf:
                    raise RuntimeError("Réponse vide : pipe fermé par l'add-in")
                raise RuntimeError("Trame incomplète reçue (pas de '\\n')")

        line = buf.split(b"\n", 1)[0].strip().lstrip(b"\xef\xbb\xbf")
        if not line:
            raise RuntimeError("Réponse vide de l'add-in")
        try:
            raw = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise RuntimeError(
                f"JSON illisible dans la réponse pipe : {e}") from e
        return ApiResponse.from_dict(raw)

    def _roundtrip(self, command: str, payload: Any = None,
                   request_id: str = "") -> ApiResponse:
        msg = PipeMessage(
            command=command,
            payload=json.dumps(payload, ensure_ascii=False) if payload is not None else "",
            request_id=request_id,
        )
        self._send(msg)
        return self._recv()

    # ------------------------------------------------------------------
    # Commandes haut niveau
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        """Vérifie que l'add-in STRUCTCALC répond (statut == ok)."""
        try:
            resp = self._roundtrip("PING")
        except Exception:
            return False
        return (resp.success and isinstance(resp.data, dict)
                and resp.data.get("status") == "ok")

    def read_model(self) -> ApiResponse:
        """Demande la lecture complète du modèle Revit (READ_MODEL)."""
        return self._roundtrip("READ_MODEL")

    def apply_changes(self, changes: dict) -> ApiResponse:
        """Envoie des modifications à appliquer dans Revit (APPLY_CHANGES)."""
        return self._roundtrip("APPLY_CHANGES", changes)

    def write_model(self, request: dict = None) -> ApiResponse:
        """Alias WRITE_MODEL (mêmes changements, commande historique)."""
        return self._roundtrip("WRITE_MODEL", request or {})

    # ------------------------------------------------------------------
    # Helpers DTO
    # ------------------------------------------------------------------
    @staticmethod
    def serialize_dto(obj: Any) -> str:
        """Sérialise un DTO (dataclass, dict, ...) en JSON compact."""
        return json.dumps(obj, ensure_ascii=False,
                          default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else o.__dict__)

    @staticmethod
    def deserialize_dto(json_str: str, cls: type = dict) -> Any:
        """Désérialise une charge utile JSON (dict par défaut)."""
        return json.loads(json_str)


# ---------------------------------------------------------------------------
# Utilitaire ligne de commande (diagnostic terrain)
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Client STRUCTCALC PRO Revit Add-in")
    parser.add_argument("command", choices=["ping", "read"],
                        help="Commande à exécuter")
    parser.add_argument("--pipe", default="structcalc_revit", help="Nom du pipe")
    args = parser.parse_args()

    client = RevitAddinClient(pipe_name=args.pipe)
    print(f"Connexion au pipe '{args.pipe}'...")
    if not client.connect(retries=3, delay_s=0.2):
        print("ÉCHEC : pipe introuvable.")
        print("Vérifiez : 1) Revit 2027 ouvert 2) add-in STRUCTCALC chargé "
              "(Addins\\2027\\StructCalcAddin.addin) 3) pipe démarré")
        sys.exit(1)

    try:
        if args.command == "ping":
            ok = client.ping()
            print(f"PING : {'OK' if ok else 'ÉCHEC'}")
            sys.exit(0 if ok else 2)
        else:
            resp = client.read_model()
            print(f"READ_MODEL : success={resp.success}")
            if resp.success and isinstance(resp.data, dict):
                d = resp.data
                print(f"  nœuds={len(d.get('nodes') or [])} "
                      f"barres={len(d.get('bars') or [])} "
                      f"cas={len(d.get('loadCases') or [])}")
                for n in (d.get("notes") or [])[:6]:
                    print(f"  note: {n}")
            else:
                print(f"  Erreur : {resp.error}")
                sys.exit(2)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
