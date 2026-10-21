# -*- coding: utf-8 -*-
"""
integration/revit/protocol.py — Client Named Pipe NDJSON vers l'add-in Revit.

Protocole (contrat strict, DTO C# côté add-in) :
  - Enveloppe : {success: bool, data: any, error: string, request_id: string}
  - Transport : NDJSON (une ligne JSON par message) sur \\.\pipe\structcalc_revit
  - Commandes : PING, READ_MODEL, APPLY_CHANGES
  - Unités : MÈTRES (Python) -> PIEDS (Revit, conversion côté add-in)
  - Aucune exception silencieuse : tout échec = message d'erreur explicite.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

PIPE_NAME = r"\\.\pipe\structcalc_revit"
READ_TIMEOUT_SEC = 30.0
WRITE_TIMEOUT_SEC = 30.0


@dataclass
class PipeEnvelope:
    success: bool
    data: Any
    error: str
    request_id: str

    @staticmethod
    def ok(data: Any, request_id: str) -> "PipeEnvelope":
        return PipeEnvelope(True, data, "", request_id)

    @staticmethod
    def fail(error: str, request_id: str) -> "PipeEnvelope":
        return PipeEnvelope(False, None, error, request_id)


class RevitPipeError(Exception):
    """Erreur de communication pipe (connexion, timeout, protocole)."""
    pass


class RevitProtocolError(Exception):
    """Erreur de protocole (enveloppe invalide, succès=false)."""
    pass


class RevitPipeClient:
    """
    Client synchrone (request/response) vers l'add-in Revit.

    Usage:
        client = RevitPipeClient()
        try:
            client.connect()
            model = client.read_model()
            client.apply_changes(changes_request)
        finally:
            client.close()
    """

    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name
        self._pipe: Optional[int] = None
        self._connected = False

    def connect(self, retries: int = 12, delay: float = 1.5) -> None:
        """Connexion avec retry (l'add-in peut ne pas être prêt immédiatement)."""
        last_err = None
        for _ in range(retries):
            try:
                # Windows Named Pipe via CreateFile (via socket hack ne marche pas,
                # on utilise le module win32file si dispo, sinon fallback)
                self._pipe = self._open_pipe()
                self._connected = True
                return
            except Exception as exc:
                last_err = exc
                time.sleep(delay)
        raise RevitPipeError(f"Connexion pipe impossible après {retries} essais : {last_err}")

    def _open_pipe(self) -> int:
        """Ouvre le named pipe Windows (CreateFile via ctypes/win32file)."""
        try:
            import win32file
            import pywintypes
        except ImportError as exc:
            raise RevitPipeError(f"pywin32 requis pour Named Pipe : {exc}")

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_FLAG_OVERLAPPED = 0x40000000

        handle = win32file.CreateFile(
            self.pipe_name,
            GENERIC_READ | GENERIC_WRITE,
            0,  # no sharing
            None,  # default security
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        return handle

    def close(self) -> None:
        if self._pipe is not None:
            try:
                import win32file
                win32file.CloseHandle(self._pipe)
            except Exception:
                pass
            self._pipe = None
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._pipe is not None

    # ------------------------------------------------------------------
    # Primitives bas niveau (NDJSON line-oriented)
    # ------------------------------------------------------------------

    def _send_line(self, line: str) -> None:
        if not self._connected or self._pipe is None:
            raise RevitPipeError("Pipe non connecté")
        try:
            import win32file
            data = (line + "\n").encode("utf-8")
            win32file.WriteFile(self._pipe, data)
        except Exception as exc:
            raise RevitPipeError(f"Écriture pipe échouée : {exc}")

    def _read_line(self, timeout: float = READ_TIMEOUT_SEC) -> str:
        if not self._connected or self._pipe is None:
            raise RevitPipeError("Pipe non connecté")
        try:
            import win32file
            import pywintypes
            deadline = time.time() + timeout
            buffer = b""
            while time.time() < deadline:
                try:
                    hr, data = win32file.ReadFile(self._pipe, 4096)
                    if not data:
                        time.sleep(0.01)
                        continue
                    buffer += data
                    if b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        return line.decode("utf-8")
                except pywintypes.error as exc:
                    if exc.winerror == 232:  # ERROR_NO_DATA
                        time.sleep(0.01)
                        continue
                    raise
            raise RevitPipeError(f"Timeout lecture pipe ({timeout}s)")
        except Exception as exc:
            raise RevitPipeError(f"Lecture pipe échouée : {exc}")

    def _request(self, command: str, payload: Any = None) -> Any:
        """Envoie une commande et attend la réponse (request/response synchrone)."""
        req_id = str(uuid.uuid4())[:8]
        msg = {
            "command": command,
            "payload": payload,
            "request_id": req_id,
        }
        self._send_line(json.dumps(msg, separators=(",", ":")))
        line = self._read_line()
        env = json.loads(line)
        envelope = PipeEnvelope(
            success=env.get("success", False),
            data=env.get("data"),
            error=env.get("error", ""),
            request_id=env.get("request_id", ""),
        )
        if not envelope.success:
            raise RevitProtocolError(f"Commande {command} échouée : {envelope.error}")
        return envelope.data

    # ------------------------------------------------------------------
    # Commandes haut niveau
    # ------------------------------------------------------------------

    def ping(self) -> Dict[str, Any]:
        """Health check : retourne info pipe (état, clients connectés)."""
        return self._request("PING")

    def read_model(self) -> Dict[str, Any]:
        """Lit le modèle Revit complet (StructuralModelDto)."""
        return self._request("READ_MODEL")

    def apply_changes(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applique les changements (sections + armatures) sur le modèle Revit.

        `changes` = dict conforme à ApplyChangesRequest :
          {
            "barChanges": [
              {
                "elementId": int,
                "newSectionName": str,
                "newSection": { "width": float, "height": float, ... },
                "rebars": [
                  { "barId": int, "diameterMm": int, "count": int,
                    "position": float, "layer": str }
                ]
              }
            ],
            "nodeChanges": [ { "elementId": int, "newSupport": {...} } ]
          }
        """
        return self._request("APPLY_CHANGES", changes)


# ---------------------------------------------------------------------------
# Utilitaires de conversion d'unités (Python m -> Revit ft fait côté add-in)
# Mais pour les diamètres d'armature : l'add-in attend mm (int) — on envoie en mm.
# ---------------------------------------------------------------------------

MM_TO_FT = 1.0 / 304.8
M_TO_FT = 1.0 / 0.3048