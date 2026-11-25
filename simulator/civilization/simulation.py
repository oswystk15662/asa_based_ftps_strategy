"""A deterministic world tick and resource accounting."""
from collections import Counter

from .economy import REMOTE_PERIOD, advance_city, build
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

    def diplomacy(self):
        pressure = Counter()
        for city in self.cities.values():
            if city["stock"]["food"] < max(1, city["population"] // 10):
                pressure[city["faction"]] += 1
        for relation in self.state["relations"]:
            a, b = relation["factions"]
            relation["tension"] = max(0, min(8, relation["tension"] + (1 if pressure[a] and pressure[b] else -1)))
            tension = relation["tension"]
            status = "conflict" if tension >= 5 else "strained" if tension >= 2 else "trade"
            if status != relation["status"]:
                relation["status"] = status
                self.event("diplomacy", factions=[a, b], status=status, tension=tension)
            if status == "conflict" and self.tick % REMOTE_PERIOD == 0:
                losses = {}
                for faction in (a, b):
                    eligible = sorted(name for name, city in self.cities.items() if city["faction"] == faction)
                    name = min(eligible, key=lambda city: self.cities[city]["stock"]["food"])
                    city = self.cities[name]
                    loss = min(city["population"] - 1, max(1, city["population"] // 20))
                    city["population"] -= loss
                    losses[name] = loss
                self.event("abstract_conflict", factions=[a, b], losses=losses)

    def step(self):
        before = self.totals()
        for name, city in sorted(self.cities.items()):
            advance_city(self, name, city)
            build(self, name, city)
        self.diplomacy()
        run_logistics(self)
        after = self.totals()
        for resource in RESOURCES:
            if after[resource] != before[resource] + self.balance[resource]:
                raise RuntimeError(f"Resource conservation failed: {resource}")
        self.state["tick"] = self.tick
        self.state["roads"] = sorted(self.roads)
        return self.state, self.events
