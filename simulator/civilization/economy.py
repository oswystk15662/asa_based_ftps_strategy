"""City production, population, and construction state."""
from .terrain import tile_key

REMOTE_PERIOD = 4


def advance_city(sim, name, city):
    elapsed = sim.tick - city["last_economy"]
    active = name in sim.state["focus"]
    city["detail"] = "active" if active else "remote"
    if not active and sim.tick % REMOTE_PERIOD:
        return
    city["last_economy"] = sim.tick
    stock = city["stock"]
    jobs = sorted(resource for resource, capacity in city["capacity"].items() if capacity)
    workers = {}
    if jobs:
        share, remainder = divmod(max(1, city["population"] // 3), len(jobs))
        workers = {resource: share + (index < remainder) for index, resource in enumerate(jobs)}
    if workers != city.get("workers", {}):
        city["workers"] = workers
        sim.event("workforce", city=name, workers=workers)
    for resource, capacity in sorted(city["capacity"].items()):
        regenerated = min(capacity, city["nodes"][resource] + max(1, capacity // 4) * elapsed)
        harvest = min(regenerated, workers.get(resource, 0) * elapsed)
        city["nodes"][resource] = regenerated - harvest
        sim.stock(name, resource, harvest, "harvest", external=True)
    need = max(1, city["population"] // 10) * elapsed
    fed = min(need, stock["food"])
    sim.stock(name, "food", -fed, "provisions", external=True)
    if fed < need:
        loss = min(city["population"] - 1, need - fed)
        city["population"] -= loss
        if loss:
            sim.event("population", city=name, change=-loss, reason="shortage")
    elif city["foundation"] and city["foundation"]["status"] == "built" and stock["food"] >= 2 * need:
        city["population"] += 1
        sim.event("population", city=name, change=1, reason="growth")


def build(sim, name, city):
    site = city["foundation"]
    if site is None and city["stock"]["wood"] >= 4:
        sim.stock(name, "wood", -4, "foundation_reserve")
        city["foundation"] = {"command_id": f"foundation:{name}", "status": "reserved",
                              "cell": city["cell"], "wood": 4}
        sim.event("construction_reserved", city=name, **city["foundation"])
        return
    if site is None:
        return
    if site["status"] == "reserved":
        cell = tile_key(site["cell"])
        building = sim.state["virtual_buildings"].setdefault(cell, site["command_id"])
        if building != site["command_id"]:
            site["status"] = "blocked"
            sim.stock(name, "wood", site["wood"], "foundation_release")
            sim.event("construction_rejected", city=name, reason="occupied", **site)
            return
        site["status"] = "built"
        sim.balance["wood"] -= site["wood"]
        sim.event("construction_confirmed", city=name, **site)
    if site["status"] != "built":
        return
    stock = city["stock"]
    if city["industry"] == "none" and stock["wood"] >= 7 and stock["ore"] >= 2 and city["population"] >= 10:
        sim.stock(name, "wood", -5, "smelter", external=True)
        sim.stock(name, "ore", -2, "smelter", external=True)
        city["industry"] = "smelter"
        sim.event("industry", city=name, stage="smelter")
    elif city["industry"] == "smelter" and stock["metal"] >= 5 and stock["wood"] >= 5:
        sim.stock(name, "metal", -5, "power_plant", external=True)
        sim.stock(name, "wood", -3, "power_plant", external=True)
        city["industry"] = "powered"
        sim.event("industry", city=name, stage="powered")
    if city["industry"] != "none" and city["last_economy"] == sim.tick:
        fuel = max(0, stock["wood"] - 2)
        # Power consumes one extra wood while processing a double batch.
        powered = city["industry"] == "powered" and fuel >= 3 and stock["ore"] >= 4
        if powered != city.get("power_online", False):
            city["power_online"] = powered
            sim.event("power", city=name, online=powered)
        units = min(stock["ore"] // 2, fuel, 2 if powered else 1)
        if powered:
            sim.stock(name, "wood", -1, "power_fuel", external=True)
        sim.stock(name, "ore", -2 * units, "smelt", external=True)
        sim.stock(name, "wood", -units, "smelt", external=True)
        sim.stock(name, "metal", units, "smelt", external=True)
