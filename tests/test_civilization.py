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


if __name__ == "__main__":
    unittest.main()
