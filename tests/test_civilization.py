from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from simulator.civilization import Simulation, advance, connect, initialize, load_world, shortest_path, start


def demo():
    path = Path(__file__).resolve().parents[1] / "configs" / "estuary-demo.json"
    return json.loads(path.read_text(encoding="utf-8"))


class CivilizationTest(unittest.TestCase):
    def test_road_respects_water_and_buildings(self):
        grid = ["..~..", ".....", "..#.."]
        route = shortest_path(grid, set(), (0, 0), (4, 0), {(1, 0)})
        self.assertEqual((0, 0), route[0])
        self.assertEqual((4, 0), route[-1])
        self.assertNotIn((2, 0), route)
        self.assertNotIn((1, 0), route)
        self.assertEqual([], shortest_path([".~."], set(), (0, 0), (2, 0)))
        self.assertEqual([], shortest_path([".~."], set(), (1, 0), (1, 0)))
        scenario = demo()
        claims = initialize(scenario)["territory"]
        self.assertEqual("Harbor", claims["1,2"])
        self.assertNotIn("4,2", claims)
        scenario["cities"][0]["cell"] = [4, 0]
        with self.assertRaises(ValueError):
            initialize(scenario)

    def test_restart_replays_identical_economy_and_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "world.sqlite"
            with closing(connect(path)) as db:
                start(db, demo())
                early = advance(db, 1)
                self.assertEqual("reserved", early["cities"]["Harbor"]["foundation"]["status"])
                with self.assertRaises(sqlite3.IntegrityError):
                    start(db, demo())
            with closing(connect(path)) as db, closing(connect(":memory:")) as replay:
                start(replay, demo())
                result = advance(db, 31)
                self.assertEqual(advance(replay, 32), result)
                query = "SELECT tick, sequence, body FROM events ORDER BY tick, sequence"
                actual = db.execute(query).fetchall()
                self.assertEqual(replay.execute(query).fetchall(), actual)
                events = [json.loads(row[2]) for row in actual]
                for kind in ("construction_confirmed", "road_built", "dispatch", "delivery", "industry"):
                    self.assertIn(kind, {event["kind"] for event in events})
                commands = [e["command_id"] for e in events if e["kind"] == "construction_confirmed"]
                self.assertCountEqual(commands, [f"foundation:{city}" for city in result["cities"]])
                self.assertEqual("active", result["cities"]["Harbor"]["detail"])
                self.assertEqual("remote", result["cities"]["Quarry"]["detail"])

    def test_failed_event_commit_rolls_back_state(self):
        with closing(connect(":memory:")) as db:
            start(db, demo())
            db.execute("CREATE TRIGGER fail BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'fail'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                advance(db, 1)
            self.assertEqual(0, load_world(db)["tick"])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def test_occupied_virtual_cell_releases_foundation_reservation(self):
        scenario = {"grid": ["."], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 2, "stock": {"wood": 4}},
        ]}
        state, _ = Simulation(initialize(scenario)).step()
        self.assertEqual("reserved", state["cities"]["A"]["foundation"]["status"])
        state["virtual_buildings"]["0,0"] = "existing"
        state, events = Simulation(state).step()
        self.assertEqual("blocked", state["cities"]["A"]["foundation"]["status"])
        self.assertEqual(4, state["cities"]["A"]["stock"]["wood"])
        self.assertEqual("existing", state["virtual_buildings"]["0,0"])
        self.assertEqual(1, sum(event["kind"] == "construction_rejected" for event in events))

    def test_abstract_conflict_logs_bounded_losses(self):
        scenario = {"grid": ["....."], "focus": ["A", "B"], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 20},
            {"id": "B", "faction": "b", "cell": [4, 0], "population": 20},
        ]}
        with closing(connect(":memory:")) as db:
            start(db, scenario)
            state = advance(db, 8)
            self.assertEqual("conflict", state["relations"][0]["status"])
            events = [json.loads(body) for body, in db.execute("SELECT body FROM events")]
            [war] = [event for event in events if event["kind"] == "abstract_conflict"]
            self.assertEqual({"A": 1, "B": 1}, war["losses"])
            self.assertTrue(all(city["population"] > 0 for city in state["cities"].values()))

    def test_closure_waits_existing_cargo_and_detours_new_cargo_across_restart(self):
        scenario = {"grid": ["...", "..."], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 2,
             "stock": {"food": 50, "wood": 50}},
            {"id": "B", "faction": "a", "cell": [2, 0], "population": 2},
        ], "road_closures": [{"from": [0, 0], "to": [1, 0], "start": 2, "end": 4}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "roads.sqlite"
            with closing(connect(path)) as db:
                start(db, scenario)
                first = advance(db, 2)
                old, detour = first["shipments"]
                self.assertTrue(old["waiting"])
                self.assertNotIn("0,0|1,0", detour["edges"])
            with closing(connect(path)) as db, closing(connect(":memory:")) as replay:
                start(replay, scenario)
                self.assertEqual(advance(replay, 7), advance(db, 5))
                rows = db.execute("SELECT tick, body FROM events ORDER BY tick, sequence")
                events = [(tick, json.loads(body)) for tick, body in rows]
                self.assertIn((2, {"kind": "shipment_waiting", "shipment_id": old["id"]}), events)
                self.assertIn((4, {"kind": "shipment_resumed", "shipment_id": old["id"]}), events)
                self.assertIn((5, {"kind": "delivery", "shipment_id": old["id"], "destination": "B"}), events)

    def test_alliance_degrades_until_food_shipment_triggers_ceasefire(self):
        scenario = {"grid": ["." * 19] * 2, "focus": ["A", "B", "Donor"], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 20},
            {"id": "B", "faction": "b", "cell": [18, 0], "population": 20},
            {"id": "Donor", "faction": "donor", "cell": [9, 0], "population": 20,
             "stock": {"food": 200, "wood": 100}, "renewal": {"food": 12}},
        ], "alliances": [["a", "b"]]}
        with closing(connect(":memory:")) as db:
            start(db, scenario)
            self.assertEqual("allied", load_world(db)["relations"][0]["status"])
            advance(db, 20)
            rows = db.execute("SELECT body FROM events ORDER BY tick, sequence")
            events = [json.loads(body) for body, in rows]
            transitions = [e["status"] for e in events
                           if e["kind"] == "diplomacy" and e["factions"] == ["a", "b"]]
            self.assertEqual(["strained", "conflict", "ceasefire"], transitions[:3])

    def test_workforce_and_power_fuel_share_the_same_ledger(self):
        scenario = {"grid": ["."], "focus": ["A"], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 9,
             "stock": {"food": 20, "wood": 4, "ore": 8},
             "renewal": {"food": 8, "ore": 8, "wood": 0}},
        ]}
        state, _ = Simulation(initialize(scenario)).step()
        state, _ = Simulation(state).step()
        city = state["cities"]["A"]
        self.assertEqual({"food": 2, "ore": 1}, city["workers"])
        city["industry"] = "powered"
        city["stock"]["wood"] = 5
        state, events = Simulation(state).step()
        self.assertIn({"kind": "power", "city": "A", "online": True}, events)
        self.assertEqual(2, city["stock"]["metal"])
        self.assertEqual(2, city["stock"]["wood"])
        _, events = Simulation(state).step()
        self.assertIn({"kind": "power", "city": "A", "online": False}, events)
        self.assertEqual(2, city["stock"]["metal"])

    def test_focus_change_after_restart_accounts_for_pending_ticks_once(self):
        scenario = {"grid": ["."], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 2, "renewal": {"food": 8}},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "focus.sqlite"
            with closing(connect(path)) as db:
                start(db, scenario)
                self.assertEqual(0, advance(db, 2)["cities"]["A"]["last_economy"])
            with closing(connect(path)) as db:
                with self.assertRaises(ValueError):
                    advance(db, 1, focus=["unknown"])
                self.assertEqual(2, load_world(db)["tick"])
                active = advance(db, 1, focus=["A"])["cities"]["A"]
                self.assertEqual(("active", 3), (active["detail"], active["last_economy"]))
                remote = advance(db, 1, focus=[])["cities"]["A"]
                self.assertEqual(("remote", 4), (remote["detail"], remote["last_economy"]))
                rows = db.execute("SELECT tick, body FROM events ORDER BY tick, sequence")
                events = [(tick, json.loads(body)) for tick, body in rows]
                harvest = [(tick, event["quantity"]) for tick, event in events if event.get("reason") == "harvest"]
                self.assertEqual([(3, 3), (4, 1)], harvest)

    def test_old_checkpoint_resumes_without_rewriting_its_events(self):
        with closing(connect(":memory:")) as db:
            start(db, demo())
            old = advance(db, 1)
            old["model"] = 1
            old.pop("road_closures")
            for city in old["cities"].values():
                city.pop("workers", None)
            with db:
                db.execute("UPDATE world SET state=? WHERE singleton=1", (json.dumps(old),))
            prior = db.execute("SELECT * FROM events WHERE tick=1 ORDER BY sequence").fetchall()
            current = advance(db, 1)
            self.assertEqual((2, 2), (current["tick"], current["model"]))
            self.assertEqual(prior, db.execute("SELECT * FROM events WHERE tick=1 ORDER BY sequence").fetchall())
            event = db.execute("SELECT body FROM events WHERE tick=2 AND sequence=0").fetchone()
            self.assertEqual({"kind": "model_upgraded", "previous": 1, "model": 2}, json.loads(event[0]))


if __name__ == "__main__":
    unittest.main()
