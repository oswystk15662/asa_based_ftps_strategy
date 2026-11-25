import sqlite3
import unittest
import uuid

from simulator.inventory_mirror import InventoryMirror
from simulator.phase1 import Bridge


class InventoryMirrorTest(unittest.TestCase):
    def test_commit_before_ack_and_reconcile_across_restart(self):
        with sqlite3.connect(":memory:") as db:
            mirror = InventoryMirror(db, 42)
            bridge = Bridge("phase1", inventory_mirror=mirror)
            start = {"protocol": 1, "world_id": "phase1", "boot_id": str(uuid.uuid4())}
            code, hello = bridge.handle("/v1/hello", start)
            self.assertEqual(200, code)
            snapshot = {"map": "Trial", "players": 0, "game_seconds": 1,
                        "inventory": {"structure_id": 42, "wood": 4}}
            request = {**start, "seq": 1, "command_id": hello["command"]["command_id"], "snapshot": snapshot}
            self.assertEqual(200, bridge.handle("/v1/exchange", request)[0])
            self.assertEqual(200, bridge.handle("/v1/exchange", request)[0])
            self.assertEqual((start["boot_id"], 1, 4), db.execute(
                "SELECT boot_id, seq, wood FROM inventory_current").fetchone())

            restarted = Bridge("phase1", inventory_mirror=mirror)
            self.assertEqual(1, restarted.handle("/v1/hello", start)[1]["ack"])
            next_boot = {**start, "boot_id": str(uuid.uuid4())}
            _, hello = restarted.handle("/v1/hello", next_boot)
            empty = {**snapshot, "inventory": {"structure_id": 42, "wood": 0}}
            request = {**next_boot, "seq": 1, "command_id": hello["command"]["command_id"], "snapshot": empty}
            wrong_id = {**request, "snapshot": {**empty, "inventory": {"structure_id": 2, "wood": 1}}}
            self.assertEqual(409, restarted.handle("/v1/exchange", wrong_id)[0])
            self.assertEqual(200, restarted.handle("/v1/exchange", request)[0])
            self.assertEqual(409, restarted.handle("/v1/hello", start)[0])
            self.assertEqual((next_boot["boot_id"], 1, 0), db.execute(
                "SELECT boot_id, seq, wood FROM inventory_current").fetchone())
