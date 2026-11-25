"""Scenario validation and initial world state."""
from .terrain import TERRAIN_COST, claim_territory, road_key
from .technology import TECHNOLOGY_RESOURCE

MODEL_VERSION = 2
RESOURCES = ("food", "wood", "ore", "metal")


def road_closures(grid, entries):
    if not isinstance(entries, list):
        raise ValueError("Expected a list of road closures")
    closures = []
    for entry in entries:
        fields = ("from", "to", "start", "end")
        if not isinstance(entry, dict) or not all(field in entry for field in fields):
            raise ValueError("Road closure requires from, to, start and end")
        a, b, start, end = (entry[field] for field in fields)
        for cell in (a, b):
            if not isinstance(cell, list) or len(cell) != 2 or any(type(n) is not int for n in cell):
                raise ValueError("Invalid road closure coordinates")
            x, y = cell
            if not (0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] in TERRAIN_COST):
                raise ValueError("Road closure requires traversable cells")
        if sum(abs(x - y) for x, y in zip(a, b)) != 1 or not (
            type(start) is int and type(end) is int and 1 <= start < end
        ):
            raise ValueError("Road closure requires an adjacent edge and a positive tick interval")
        closures.append({"edge": road_key(a, b), "start": start, "end": end})
    return sorted(closures, key=lambda entry: (entry["start"], entry["end"], entry["edge"]))


def validate_focus(cities, focus):
    if not isinstance(focus, list) or any(not isinstance(city, str) or city not in cities for city in focus):
        raise ValueError("Focus must name existing cities")
    return sorted(set(focus))


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
        technology = entry.get("technology")
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
        if technology is not None and (not isinstance(technology, str) or technology not in TECHNOLOGY_RESOURCE):
            raise ValueError(f"Unknown starting technology for {name}")
        cities[name] = {
            "faction": faction, "cell": point, "population": population,
            "stock": {resource: stock.get(resource, 0) for resource in RESOURCES},
            "capacity": renewal, "nodes": renewal.copy(), "foundation": None,
            "industry": "none", "last_economy": 0, "detail": "remote",
        }
        if technology is not None:
            cities[name]["technology"] = technology
    if not cities:
        raise ValueError("At least one city is required")
    focus = validate_focus(cities, scenario.get("focus", []))
    factions = sorted({city["faction"] for city in cities.values()})
    alliances = set()
    entries = scenario.get("alliances", [])
    if not isinstance(entries, list):
        raise ValueError("Expected a list of alliances")
    for pair in entries:
        if (not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]
                or any(not isinstance(name, str) or name not in factions for name in pair)):
            raise ValueError("An alliance requires two distinct existing factions")
        alliances.add(tuple(sorted(pair)))
    relations = []
    for i, source in enumerate(factions):
        for destination in factions[i + 1:]:
            status = "allied" if (source, destination) in alliances else "neutral"
            relations.append({"factions": [source, destination], "tension": 0, "status": status})
    return {
        "model": MODEL_VERSION, "tick": 0, "grid": grid, "focus": focus,
        "cities": cities, "roads": [], "shipments": [], "next_shipment": 1,
        "relations": relations, "territory": claim_territory(grid, cities), "virtual_buildings": {},
        "road_closures": road_closures(grid, scenario.get("road_closures", [])),
    }
