"""Deterministic, standalone civilization simulation on a finite grid."""
import argparse
from collections import Counter
from contextlib import closing
import heapq
import json
from pathlib import Path
import sqlite3

MODEL_VERSION = 1
RESOURCES = ("food", "wood", "ore", "metal")
ROAD_CAPACITY = 4
REMOTE_PERIOD = 4
MAX_ROUTE_ATTEMPTS = 8
TERRAIN_COST = {".": 2, "^": 5}


def tile_key(point):
    return f"{point[0]},{point[1]}"


def road_key(a, b):
    return "|".join(sorted((tile_key(a), tile_key(b))))


def shortest_path(grid, roads, start, end, occupied=()):
    start, end = tuple(start), tuple(end)
    for x, y in (start, end):
        if not 0 <= y < len(grid) or not 0 <= x < len(grid[y]) or grid[y][x] not in TERRAIN_COST:
            return []
    if start == end:
        return [start]
    blocked = set(occupied) - {start, end}
    distance = {start: 0}
    previous = {}
    queue = [(0, start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != distance[cell]:
            continue
        if cell == end:
            route = [cell]
            while cell != start:
                cell = previous[cell]
                route.append(cell)
            return route[::-1]
        x, y = cell
        for next_cell in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = next_cell
            if not 0 <= ny < len(grid) or not 0 <= nx < len(grid[ny]) or next_cell in blocked:
                continue
            terrain = grid[ny][nx]
            if terrain not in TERRAIN_COST:
                continue
            candidate = cost + (1 if road_key(cell, next_cell) in roads else TERRAIN_COST[terrain])
            if candidate >= distance.get(next_cell, float("inf")):
                continue
            previous[next_cell] = cell
            distance[next_cell] = candidate
            heapq.heappush(queue, (candidate, next_cell))
    return []


def claim_territory(grid, cities):
    claims = {tuple(city["cell"]): (0, name) for name, city in cities.items()}
    border = [(distance, name, point) for point, (distance, name) in claims.items()]
    heapq.heapify(border)
    while border:
        distance, name, point = heapq.heappop(border)
        if claims[point] != (distance, name):
            continue
        x, y = point
        for nx, ny in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            if not 0 <= ny < len(grid) or not 0 <= nx < len(grid[ny]):
                continue
            cost = TERRAIN_COST.get(grid[ny][nx])
            if cost is None:
                continue
            candidate = (distance + cost, name)
            if candidate >= claims.get((nx, ny), (float("inf"), name)):
                continue
            claims[nx, ny] = candidate
            heapq.heappush(border, (*candidate, (nx, ny)))
    return {tile_key(point): city for point, (_, city) in claims.items()}


def initialize(scenario):
    grid = scenario["grid"]
    if not isinstance(grid, list) or not grid or not grid[0] or any(
        not isinstance(row, str) or len(row) != len(grid[0]) or set(row) - set(".^~#?")
        for row in grid
    ):
        raise ValueError("Expected a rectangular terrain grid")
    cities = {}
    used_cells = set()
    for entry in scenario["cities"]:
        name, faction, point = entry["id"], entry["faction"], entry["cell"]
        population = entry["population"]
        stock = entry.get("stock", {})
        renewal = entry.get("renewal", {})
        if not isinstance(name, str) or not name or name in cities or not isinstance(faction, str) or not faction:
            raise ValueError("Each city requires a unique name and a faction")
        if not isinstance(point, list) or len(point) != 2 or any(type(n) is not int for n in point):
            raise ValueError("Invalid city coordinates")
        x, y = point
        if (not 0 <= y < len(grid) or not 0 <= x < len(grid[0]) or
                grid[y][x] != "." or tuple(point) in used_cells):
            raise ValueError("City sites must be distinct flat cells")
        used_cells.add(tuple(point))
        if type(population) is not int or population < 1:
            raise ValueError("Population must be a positive integer")
        if not isinstance(stock, dict) or not isinstance(renewal, dict):
            raise ValueError("Expected stock and renewal maps")
        if set(stock) - set(RESOURCES) or set(renewal) - {"food", "wood", "ore"}:
            raise ValueError("Unknown resource")
        if any(type(n) is not int or n < 0 for n in (*stock.values(), *renewal.values())):
            raise ValueError("Resource quantities must be nonnegative integers")
        cities[name] = {
            "faction": faction, "cell": point, "population": population,
            "stock": {resource: stock.get(resource, 0) for resource in RESOURCES},
            "capacity": renewal, "nodes": renewal.copy(), "foundation": None,
            "industry": "none", "last_economy": 0, "detail": "remote",
        }
    if not cities:
        raise ValueError("At least one city is required")
    focus = scenario.get("focus", [])
    if not isinstance(focus, list) or any(not isinstance(city, str) or city not in cities for city in focus):
        raise ValueError("Focus must name existing cities")
    factions = sorted({city["faction"] for city in cities.values()})
    relations = []
    for i, source in enumerate(factions):
        for destination in factions[i + 1:]:
            relations.append({"factions": [source, destination], "tension": 0, "status": "neutral"})
    return {
        "model": MODEL_VERSION, "tick": 0, "grid": grid, "focus": sorted(set(focus)),
        "cities": cities, "roads": [], "shipments": [], "next_shipment": 1,
        "relations": relations, "territory": claim_territory(grid, cities), "virtual_buildings": {},
    }


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

    def economy(self, name, city):
        elapsed = self.tick - city["last_economy"]
        active = name in self.state["focus"]
        city["detail"] = "active" if active else "remote"
        if not active and self.tick % REMOTE_PERIOD:
            return
        city["last_economy"] = self.tick
        stock = city["stock"]
        labor = max(1, city["population"] // 8)
        for resource, capacity in sorted(city["capacity"].items()):
            regenerated = min(capacity, city["nodes"][resource] + max(1, capacity // 4) * elapsed)
            harvest = min(regenerated, labor * elapsed)
            city["nodes"][resource] = regenerated - harvest
            self.stock(name, resource, harvest, "harvest", external=True)
        need = max(1, city["population"] // 10) * elapsed
        fed = min(need, stock["food"])
        self.stock(name, "food", -fed, "provisions", external=True)
        if fed < need:
            loss = min(city["population"] - 1, need - fed)
            city["population"] -= loss
            if loss:
                self.event("population", city=name, change=-loss, reason="shortage")
        elif city["foundation"] and city["foundation"]["status"] == "built" and stock["food"] >= 2 * need:
            city["population"] += 1
            self.event("population", city=name, change=1, reason="growth")

    def build(self, name, city):
        site = city["foundation"]
        if site is None and city["stock"]["wood"] >= 4:
            self.stock(name, "wood", -4, "foundation_reserve")
            city["foundation"] = {"command_id": f"foundation:{name}", "status": "reserved",
                                  "cell": city["cell"], "wood": 4}
            self.event("construction_reserved", city=name, **city["foundation"])
            return
        if site is None:
            return
        if site["status"] == "reserved":
            cell = tile_key(site["cell"])
            building = self.state["virtual_buildings"].setdefault(cell, site["command_id"])
            if building != site["command_id"]:
                site["status"] = "blocked"
                self.stock(name, "wood", site["wood"], "foundation_release")
                self.event("construction_rejected", city=name, reason="occupied", **site)
                return
            site["status"] = "built"
            self.balance["wood"] -= site["wood"]
            self.event("construction_confirmed", city=name, **site)
        if site["status"] != "built":
            return
        stock = city["stock"]
        if city["industry"] == "none" and stock["wood"] >= 7 and stock["ore"] >= 2 and city["population"] >= 10:
            self.stock(name, "wood", -5, "smelter", external=True)
            self.stock(name, "ore", -2, "smelter", external=True)
            city["industry"] = "smelter"
            self.event("industry", city=name, stage="smelter")
        elif city["industry"] == "smelter" and stock["metal"] >= 5 and stock["wood"] >= 5:
            self.stock(name, "metal", -5, "power_plant", external=True)
            self.stock(name, "wood", -3, "power_plant", external=True)
            city["industry"] = "powered"
            self.event("industry", city=name, stage="powered")
        if city["industry"] != "none" and city["last_economy"] == self.tick:
            units = min(stock["ore"] // 2, max(0, stock["wood"] - 2),
                        2 if city["industry"] == "powered" else 1)
            self.stock(name, "ore", -2 * units, "smelt", external=True)
            self.stock(name, "wood", -units, "smelt", external=True)
            self.stock(name, "metal", units, "smelt", external=True)

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

    def logistics(self):
        reserved = Counter()
        incoming = Counter()
        travelling = []
        for shipment in self.state["shipments"]:
            if shipment["due"] <= self.tick:
                self.stock(shipment["destination"], shipment["resource"], shipment["units"], "delivery")
                self.event("delivery", shipment_id=shipment["id"], destination=shipment["destination"])
                continue
            for edge in shipment["edges"]:
                reserved[edge] += shipment["units"]
            incoming[shipment["destination"], shipment["resource"]] += shipment["units"]
            travelling.append(shipment)
        self.state["shipments"] = travelling

        # shortcut: one prioritized dispatch per tick, expand with a multi-commodity planner after profiling.
        names = sorted(self.cities)
        offset = (self.tick - 1) % len(names)
        destination_order = names[offset:] + names[:offset]
        attempts = 0
        market_closed = {
            tuple(relation["factions"]) for relation in self.state["relations"]
            if relation["status"] == "conflict"
        }
        for resource, minimum in (("food", 6), ("wood", 8), ("ore", 5)):
            for destination in destination_order:
                dest = self.cities[destination]
                deficit = minimum - dest["stock"][resource] - incoming[destination, resource]
                if deficit <= 0:
                    continue
                for source in names:
                    origin = self.cities[source]
                    if source == destination or tuple(sorted((origin["faction"], dest["faction"]))) in market_closed:
                        continue
                    offer = origin["stock"][resource] - 2 * minimum
                    if offer <= 0:
                        continue
                    attempts += 1
                    if self.dispatch(source, destination, resource, min(offer, deficit), reserved):
                        return
                    if attempts == MAX_ROUTE_ATTEMPTS:
                        return

    def dispatch(self, source, destination, resource, desired, reserved):
        origin, dest = self.cities[source], self.cities[destination]
        # Saturated edges may still be traversed by a later shipment after current arrivals.
        occupied = [tuple(city["cell"]) for city in self.cities.values()]
        route = shortest_path(self.state["grid"], self.roads, origin["cell"], dest["cell"], occupied)
        if not route:
            return False
        edges = [road_key(a, b) for a, b in zip(route, route[1:])]
        units = min(desired, *(ROAD_CAPACITY - reserved[edge] for edge in edges))
        if units <= 0:
            return False
        new_edges = set(edges) - self.roads
        available_wood = origin["stock"]["wood"] - (units if resource == "wood" else 0)
        if len(new_edges) > available_wood:
            return False
        for edge in sorted(new_edges):
            self.roads.add(edge)
            self.event("road_built", city=source, edge=edge)
        self.stock(source, "wood", -len(new_edges), "roads", external=True)
        self.stock(source, resource, -units, "dispatch")
        shipment = {
            "id": self.state["next_shipment"], "source": source, "destination": destination,
            "resource": resource, "units": units, "edges": edges, "due": self.tick + max(1, len(edges)),
        }
        self.state["next_shipment"] += 1
        self.state["shipments"].append(shipment)
        self.event("dispatch", **shipment)
        return True

    def step(self):
        before = self.totals()
        for name, city in sorted(self.cities.items()):
            self.economy(name, city)
            self.build(name, city)
        self.diplomacy()
        self.logistics()
        after = self.totals()
        for resource in RESOURCES:
            if after[resource] != before[resource] + self.balance[resource]:
                raise RuntimeError(f"Resource conservation failed: {resource}")
        self.state["tick"] = self.tick
        self.state["roads"] = sorted(self.roads)
        return self.state, self.events


def connect(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS world (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1), state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            tick INTEGER NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL,
            PRIMARY KEY (tick, sequence)
        );
    """)
    return db


def start(db, scenario):
    payload = json.dumps(initialize(scenario), sort_keys=True)
    with db:
        db.execute("INSERT INTO world VALUES (1, ?)", (payload,))


def load_world(db):
    row = db.execute("SELECT state FROM world WHERE singleton = 1").fetchone()
    if not row:
        raise ValueError("Initialize a scenario first")
    state = json.loads(row[0])
    if state["model"] != MODEL_VERSION:
        raise ValueError("Simulation model version mismatch")
    return state


def advance(db, ticks):
    if type(ticks) is not int or ticks < 0:
        raise ValueError("Ticks must be a nonnegative integer")
    for _ in range(ticks):
        with db:
            db.execute("BEGIN IMMEDIATE")
            state, events = Simulation(load_world(db)).step()
            db.execute("UPDATE world SET state = ? WHERE singleton = 1", (json.dumps(state, sort_keys=True),))
            db.executemany("INSERT INTO events VALUES (?, ?, ?)", (
                (state["tick"], i, json.dumps(event, sort_keys=True))
                for i, event in enumerate(events)
            ))
    return load_world(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--scenario", type=Path, help="Initialize a new database")
    parser.add_argument("--ticks", type=int, default=1)
    args = parser.parse_args()
    with closing(connect(args.database)) as db:
        if args.scenario:
            start(db, json.loads(args.scenario.read_text(encoding="utf-8")))
        state = advance(db, args.ticks)
    print(json.dumps({
        "tick": state["tick"], "cities": state["cities"], "roads": len(state["roads"]),
        "shipments_in_transit": len(state["shipments"]), "relations": state["relations"],
        "claimed_cells": len(state["territory"]),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
