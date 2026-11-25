"""Faction relations and abstract population losses."""
from .economy import REMOTE_PERIOD


def update_relations(sim):
    weakest = {}
    pressured = set()
    for name, city in sim.cities.items():
        faction, food = city["faction"], city["stock"]["food"]
        candidate = (food, name)
        if faction not in weakest or candidate < weakest[faction]:
            weakest[faction] = candidate
        if food < max(1, city["population"] // 10):
            pressured.add(faction)

    for relation in sim.state["relations"]:
        a, b = relation["factions"]
        change = 1 if a in pressured and b in pressured else -1
        tension = max(0, min(8, relation["tension"] + change))
        previous = relation["status"]
        if tension >= 5:
            status = "conflict"
        elif tension and previous in ("conflict", "ceasefire"):
            status = "ceasefire"
        elif tension >= 2:
            status = "strained"
        else:
            status = "allied" if previous == "allied" else "trade"
        relation.update(tension=tension, status=status)
        if status != previous:
            sim.event("diplomacy", factions=[a, b], status=status, tension=tension)
        if status == "conflict" and sim.tick % REMOTE_PERIOD == 0:
            losses = {}
            for faction in (a, b):
                name = weakest[faction][1]
                city = sim.cities[name]
                loss = min(city["population"] - 1, max(1, city["population"] // 20))
                city["population"] -= loss
                losses[name] = loss
            sim.event("abstract_conflict", factions=[a, b], losses=losses)
