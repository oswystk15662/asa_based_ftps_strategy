"""One loopback movement request per isolated ASA boot."""
import time
import uuid


class NpcMoveTrial:
    def __init__(self):
        self.boot_id = None
        self.request = None
        self.deadline = 0.0

    def observe_boot(self, boot_id):
        if self.boot_id != boot_id:
            self.boot_id = boot_id
            self.request = None

    def status(self, session):
        snapshot = session.last_snapshot if session else None
        trial = snapshot.get("npc_trial") if snapshot and snapshot["players"] == 0 else None
        if (self.request and isinstance(trial, dict) and trial.get("status") == "ready"
                and time.monotonic() >= self.deadline):
            trial = {**trial, "status": "expired", "command_id": self.request["command_id"]}
        return {"boot_id": session.boot_id if session else None,
                "trial": trial if isinstance(trial, dict) else None}

    def submit(self, session, body):
        current = self.status(session)
        if not session or body["boot_id"] != session.boot_id:
            return 409, {"error": "npc_trial_boot_mismatch"}
        if set(body) != {"protocol", "world_id", "boot_id", "command_id", "npc_id"}:
            return 400, {"error": "invalid_npc_command"}
        command_id = body.get("command_id")
        try:
            if str(uuid.UUID(command_id)) != command_id:
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            return 400, {"error": "invalid_npc_command_id"}
        npc_id = body.get("npc_id")
        if not isinstance(npc_id, str) or not npc_id.isascii() or not npc_id.isdecimal() or not 1 <= len(npc_id) <= 20:
            return 400, {"error": "invalid_npc_id"}
        request = {"command_id": command_id, "npc_id": npc_id}
        if self.request is not None:
            if self.request != request:
                return 409, {"error": "npc_trial_slot_used"}
        else:
            trial = current["trial"]
            if not trial or trial.get("status") != "ready" or trial.get("npc_id") != npc_id:
                return 409, {"error": "npc_trial_not_ready"}
            self.request = request
            self.deadline = time.monotonic() + 5.0
        return 202, {**current, "command_id": command_id}

    def delivery(self, session):
        trial = self.status(session)["trial"]
        remaining_ms = int((self.deadline - time.monotonic()) * 1000)
        if (self.request and remaining_ms > 0 and trial and trial.get("status") == "ready"
                and trial.get("npc_id") == self.request["npc_id"]):
            return {**self.request, "ttl_ms": remaining_ms}
        return None
