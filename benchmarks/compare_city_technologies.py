"""Compare city production and trade with and without starting technology."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path

from simulator.civilization import advance, connect, start

DEMO = Path(__file__).resolve().parents[1] / "configs" / "city-technology-demo.json"


def replay(scenario, ticks):
    harvested, shipped, delivered = Counter(), Counter(), Counter()
    shipments = {}
    with closing(connect(":memory:")) as db:
        start(db, scenario)
        advance(db, ticks)
        for body, in db.execute("SELECT body FROM events ORDER BY tick, sequence"):
            event = json.loads(body)
            kind = event["kind"]
            if kind == "stock" and event["reason"] == "harvest":
                harvested[event["city"], event["resource"]] += event["quantity"]
            elif kind == "dispatch":
                route = (event["source"], event["destination"], event["resource"])
                shipments[event["id"]] = (route, event["units"])
                shipped[route] += event["units"]
            elif kind == "delivery":
                route, units = shipments[event["shipment_id"]]
                delivered[route] += units
    return harvested, shipped, delivered


def without_technologies(scenario):
    return {**scenario, "cities": [{**city, "technology": None} for city in scenario["cities"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=DEMO)
    parser.add_argument("--ticks", type=int, default=12)
    args = parser.parse_args()
    if args.ticks <= 0:
        parser.error("ticks must be positive")
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    base_harvest, base_ship, base_deliver = replay(without_technologies(scenario), args.ticks)
    harvest, shipped, delivered = replay(scenario, args.ticks)
    print(f"{args.ticks} ticks (totals: no technology -> starting technology)\n")
    print("| City | Starting technology | Food | Wood | Ore |\n|---|---|---:|---:|---:|")
    for city in scenario["cities"]:
        name = city["id"]
        amounts = [f"{base_harvest[name, resource]} -> {harvest[name, resource]}"
                   for resource in ("food", "wood", "ore")]
        print("| " + " | ".join([name, city.get("technology") or "None", *amounts]) + " |")
    routes = sorted(base_ship.keys() | shipped.keys())
    if not routes:
        print("\nNo shipments in either run.")
        return
    print("\n| Shipment | Resource | Dispatched | Delivered |\n|---|---|---:|---:|")
    for source, destination, resource in routes:
        route = (source, destination, resource)
        print(f"| {source} -> {destination} | {resource} | {base_ship[route]} -> {shipped[route]} | "
              f"{base_deliver[route]} -> {delivered[route]} |")


if __name__ == "__main__":
    main()
