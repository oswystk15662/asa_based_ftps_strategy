"""Scenario validation and initial world state."""
from .terrain import claim_territory

MODEL_VERSION = 1
RESOURCES = ("food", "wood", "ore", "metal")


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
