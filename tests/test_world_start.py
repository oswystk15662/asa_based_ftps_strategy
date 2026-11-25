import json
from contextlib import closing
from pathlib import Path
import unittest

from simulator.civilization import advance, connect, initialize, start


class WorldStartTest(unittest.TestCase):
    def scenario(self):
        path = Path(__file__).resolve().parents[1] / "configs" / "established-world-demo.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_established_world_uses_existing_roads_and_facilities(self):
        with closing(connect(":memory:")) as db:
            start(db, self.scenario())
            initial = advance(db, 0)
            self.assertEqual(6, len(initial["roads"]))
            self.assertEqual(3, len(initial["virtual_buildings"]))
            self.assertEqual(64, initial["cities"]["Harbor"]["stock"]["wood"])
            self.assertIsNone(initial["cities"]["Frontier"]["foundation"])
            self.assertEqual("smelter", initial["cities"]["Mine"]["industry"])

            first = advance(db, 1)
            [shipment] = first["shipments"]
            self.assertEqual(("Harbor", "Oasis", "food"),
                             (shipment["source"], shipment["destination"], shipment["resource"]))
            self.assertTrue(set(shipment["edges"]).issubset(initial["roads"]))
            self.assertEqual(initial["roads"], first["roads"])
            self.assertGreater(first["cities"]["Mine"]["stock"]["metal"], 0)
            advance(db, shipment["due"] - 1)
            events = [json.loads(body) for body, in db.execute("SELECT body FROM events")]
            self.assertIn({"kind": "delivery", "destination": "Oasis", "shipment_id": shipment["id"]}, events)
            reservations = [event["city"] for event in events if event["kind"] == "construction_reserved"]
            self.assertEqual(["Frontier"], reservations)

    def test_invalid_inherited_road_and_facility_are_rejected(self):
        scenario = self.scenario()
        scenario["starting_roads"] = [[[2, 1], [2, 2]]]
        with self.assertRaisesRegex(ValueError, "traversable"):
            initialize(scenario)
        scenario["starting_roads"] = []
        scenario["cities"][2]["starting_foundation"] = False
        with self.assertRaisesRegex(ValueError, "requires a foundation"):
            initialize(scenario)
