import json
import unittest

from benchmarks.compare_city_technologies import DEMO, replay, without_technologies
from simulator.civilization import Simulation, initialize


class CityTechnologyTest(unittest.TestCase):
    def test_same_starting_resources_produce_specialized_trade(self):
        scenario = json.loads(DEMO.read_text(encoding="utf-8"))
        baseline = without_technologies(scenario)
        state = initialize(scenario)
        for city in state["cities"].values():
            self.assertEqual((12, 0, 12, 2), (city["population"], city["stock"]["food"],
                                             city["stock"]["wood"], city["stock"]["ore"]))
            self.assertEqual({"food": 12, "wood": 12, "ore": 12}, city["nodes"])
        base_harvest, base_ship, base_deliver = replay(baseline, 12)
        harvest, shipped, delivered = replay(scenario, 12)
        self.assertFalse(base_ship or base_deliver)
        self.assertEqual([20, 16, 19], [harvest[key] - base_harvest[key]
                                        for key in (("Coast", "food"), ("Forest", "wood"), ("Mine", "ore"))])
        self.assertEqual({("Coast", "Forest", "food"): 1, ("Forest", "Coast", "wood"): 1,
                          ("Mine", "Coast", "ore"): 2}, delivered)
        self.assertEqual(4, shipped["Forest", "Mine", "wood"])
        self.assertEqual(0, delivered["Forest", "Mine", "wood"])

    def test_technology_requires_a_known_value_and_does_not_create_resources(self):
        scenario = {"grid": ["."], "focus": ["A"], "cities": [
            {"id": "A", "faction": "a", "cell": [0, 0], "population": 12,
             "technology": "mining", "renewal": {"ore": 1}},
        ]}
        state, _ = Simulation(initialize(scenario)).step()
        city = state["cities"]["A"]
        self.assertEqual("mining", city["technology"])
        self.assertEqual((1, 0), (city["stock"]["ore"], city["nodes"]["ore"]))
        scenario["cities"][0]["technology"] = ["mining"]
        with self.assertRaisesRegex(ValueError, "Unknown starting technology"):
            initialize(scenario)
