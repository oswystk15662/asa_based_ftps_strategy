"""Road construction, shipment capacity, and delivery."""
from collections import Counter

from .terrain import road_key, shortest_path

ROAD_CAPACITY = 4
MAX_ROUTE_ATTEMPTS = 8


def closed_edges(sim):
    closures = sim.state.get("road_closures", ())
    previous = {entry["edge"] for entry in closures if entry["start"] <= sim.tick - 1 < entry["end"]}
    current = {entry["edge"] for entry in closures if entry["start"] <= sim.tick < entry["end"]}
    for edge in sorted(current - previous):
        sim.event("road_closed", edge=edge)
    for edge in sorted(previous - current):
        sim.event("road_reopened", edge=edge)
    return current


def run_logistics(sim):
    closed = closed_edges(sim)
    reserved = Counter()
    incoming = Counter()
    travelling = []
    for shipment in sim.state["shipments"]:
        if closed.intersection(shipment["edges"]):
            shipment["due"] += 1
            if not shipment.get("waiting"):
                shipment["waiting"] = True
                sim.event("shipment_waiting", shipment_id=shipment["id"])
        elif shipment.pop("waiting", False):
            sim.event("shipment_resumed", shipment_id=shipment["id"])
        if shipment["due"] <= sim.tick:
            sim.stock(shipment["destination"], shipment["resource"], shipment["units"], "delivery")
            sim.event("delivery", shipment_id=shipment["id"], destination=shipment["destination"])
            continue
        for edge in shipment["edges"]:
            reserved[edge] += shipment["units"]
        incoming[shipment["destination"], shipment["resource"]] += shipment["units"]
        travelling.append(shipment)
    sim.state["shipments"] = travelling
    unavailable = closed | {edge for edge, units in reserved.items() if units >= ROAD_CAPACITY}
    occupied = [tuple(city["cell"]) for city in sim.cities.values()]

    # shortcut: one prioritized dispatch per tick, expand with a multi-commodity planner after profiling.
    names = sorted(sim.cities)
    offset = (sim.tick - 1) % len(names)
    destination_order = names[offset:] + names[:offset]
    attempts = 0
    market_closed = {
        tuple(relation["factions"]) for relation in sim.state["relations"]
        if relation["status"] == "conflict"
    }
    for resource, minimum in (("food", 6), ("wood", 8), ("ore", 5)):
        for destination in destination_order:
            dest = sim.cities[destination]
            deficit = minimum - dest["stock"][resource] - incoming[destination, resource]
            if deficit <= 0:
                continue
            for source in names:
                origin = sim.cities[source]
                if source == destination or tuple(sorted((origin["faction"], dest["faction"]))) in market_closed:
                    continue
                offer = origin["stock"][resource] - 2 * minimum
                if offer <= 0:
                    continue
                attempts += 1
                if dispatch(sim, source, destination, resource, min(offer, deficit), reserved,
                            occupied, unavailable):
                    return
                if attempts == MAX_ROUTE_ATTEMPTS:
                    return


def dispatch(sim, source, destination, resource, desired, reserved, occupied, unavailable):
    origin, dest = sim.cities[source], sim.cities[destination]
    route = shortest_path(sim.state["grid"], sim.roads, origin["cell"], dest["cell"], occupied, unavailable)
    if not route:
        return False
    edges = [road_key(a, b) for a, b in zip(route, route[1:])]
    units = min(desired, *(ROAD_CAPACITY - reserved[edge] for edge in edges))
    if units <= 0:
        return False
    new_edges = set(edges) - sim.roads
    available_wood = origin["stock"]["wood"] - (units if resource == "wood" else 0)
    if len(new_edges) > available_wood:
        return False
    for edge in sorted(new_edges):
        sim.roads.add(edge)
        sim.event("road_built", city=source, edge=edge)
    sim.stock(source, "wood", -len(new_edges), "roads", external=True)
    sim.stock(source, resource, -units, "dispatch")
    shipment = {
        "id": sim.state["next_shipment"], "source": source, "destination": destination,
        "resource": resource, "units": units, "edges": edges, "due": sim.tick + max(1, len(edges)),
    }
    sim.state["next_shipment"] += 1
    sim.state["shipments"].append(shipment)
    sim.event("dispatch", **shipment)
    return True
