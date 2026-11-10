"""Máquina de estados SOMENTE PARA TESTE. Atuações reais estão proibidas."""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .protocol import Received

ALLOWED_NEXT = {
    "SEGURO_ESPERA": {"BUSCA"},
    "BUSCA": {"APROXIMACAO"},
    "APROXIMACAO": {"AGUARDANDO_PEGA"},
    "AGUARDANDO_PEGA": {"CAPTURA_MANUAL"},
    "CAPTURA_MANUAL": {"RETORNO", "BUSCA"},
    "RETORNO": {"DEPOSITO"},
    "DEPOSITO": {"SEGURO_ESPERA"},
}


@dataclass(frozen=True)
class Decision:
    command_id: str
    accepted: bool
    reason: str
    state: str
    # Importante: "simulated_only" não indica atuação física.
    execution: str = "simulated_only"


class SimulatedController:
    def __init__(self, heartbeat_timeout: float = 4.0):
        self.state = "SEGURO_ESPERA"
        self.last_heartbeat: Optional[float] = None
        self.session_id: Optional[str] = None
        self.heartbeat_timeout = heartbeat_timeout
        self._ids: OrderedDict[str, None] = OrderedDict()

    def heartbeat(self, packet: Received, *, at: Optional[float] = None) -> None:
        next_session = packet.data["session_id"]
        # Reinício do Node-RED = nova sessão. Não retomar estado ativo automaticamente.
        if self.session_id is not None and self.session_id != next_session:
            self.state = "SEGURO_ESPERA"
        self.session_id = next_session
        self.last_heartbeat = time.monotonic() if at is None else at

    def station_ok(self, *, at: Optional[float] = None) -> bool:
        current = time.monotonic() if at is None else at
        return (self.last_heartbeat is not None and
                current - self.last_heartbeat <= self.heartbeat_timeout)

    def watchdog(self, *, at: Optional[float] = None) -> bool:
        """Retorna True apenas quando foi necessário forçar espera segura."""
        if not self.station_ok(at=at) and self.state != "SEGURO_ESPERA":
            self.state = "SEGURO_ESPERA"
            return True
        return False

    def command(self, packet: Received, *, at: Optional[float] = None) -> Decision:
        data = packet.data
        command_id = data["command_id"]
        if command_id in self._ids:
            return Decision(command_id, False, "duplicate_command", self.state)
        self._ids[command_id] = None
        if len(self._ids) > 200:
            self._ids.popitem(last=False)

        # PARAR e SEGURO_ESPERA são aceitos em qualquer estado, sem necessidade de heartbeat.
        if ((packet.event_type == "mode_command" and data["mode"] == "SEGURO_ESPERA") or
                (packet.event_type == "manual_command" and data["action"] == "PARAR")):
            self.state = "SEGURO_ESPERA"
            return Decision(command_id, True, "safe_state_requested", self.state)

        if not self.station_ok(at=at):
            return Decision(command_id, False, "station_heartbeat_missing", self.state)

        if packet.event_type == "mode_command":
            next_state = data["mode"]
            if next_state not in ALLOWED_NEXT[self.state]:
                return Decision(command_id, False, "invalid_transition", self.state)
            self.state = next_state
            return Decision(command_id, True, "state_transition_simulated", self.state)

        # Não temos atuadores integrados: qualquer movimento é apenas reconhecido
        # no software e nunca enviado ao hardware.
        if self.state != "CAPTURA_MANUAL":
            return Decision(command_id, False, "manual_command_not_allowed_in_state", self.state)
        return Decision(command_id, True, "manual_command_received_no_actuation", self.state)
