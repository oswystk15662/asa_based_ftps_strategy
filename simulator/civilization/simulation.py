"""A deterministic world tick and resource accounting."""
from collections import Counter

from .diplomacy import update_relations
from .economy import advance_city, build
from .logistics import run_logistics
from .scenario import RESOURCES


class Simulation:
    def __init__(self, state):
        self.state = state
        self.cities = state["cities"]
        self.roads = set(state["roads"])
        self.tick = state["tick"] + 1
        self.events = []
        self.balance = Counter()

    def event(self, kind, **fields):
        self.events.append({"kind": kind, **fields})

    def stock(self, city, resource, delta, reason, *, external=False):
        if self.cities[city]["stock"][resource] + delta < 0:
            raise RuntimeError("Insufficient resources")
        self.cities[city]["stock"][resource] += delta
        if external:
            self.balance[resource] += delta
        if delta:
            self.event("stock", city=city, resource=resource, quantity=delta, reason=reason)

    def totals(self):
        totals = Counter()
        for city in self.cities.values():
            totals.update(city["stock"])
            if city["foundation"] and city["foundation"]["status"] == "reserved":
                totals["wood"] += city["foundation"]["wood"]
        for shipment in self.state["shipments"]:
            totals[shipment["resource"]] += shipment["units"]
        return totals

    def step(self):
        before = self.totals()
        for name, city in sorted(self.cities.items()):
            advance_city(self, name, city)
            build(self, name, city)
        update_relations(self)
        run_logistics(self)
        after = self.totals()
        for resource in RESOURCES:
            if after[resource] != before[resource] + self.balance[resource]:
                raise RuntimeError(f"Resource conservation failed: {resource}")
        self.state["tick"] = self.tick
        self.state["roads"] = sorted(self.roads)
        return self.state, self.events
