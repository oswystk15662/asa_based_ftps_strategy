"""Measure a reproducible 30-city aggregate scenario using a disk-backed SQLite database."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
from time import perf_counter

from simulator.civilization import advance, connect, start


def scenario():
    return {
        "grid": ["." * 60 for _ in range(50)],
        "focus": ["City 00"],
        "cities": [
            {"id": f"City {i:02}", "faction": f"Faction {i % 3}",
             "cell": [i % 6 * 9 + 2, i // 6 * 9 + 2], "population": 1000,
             "stock": {"food": 0 if i % 2 else 3000, "wood": 1500, "ore": 120},
             "renewal": {"food": 0 if i % 2 else 2000, "wood": 250, "ore": 80}}
            for i in range(30)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=80)
    args = parser.parse_args()
    if args.ticks <= 0:
        parser.error("ticks must be positive")
    with TemporaryDirectory() as folder:
        path = Path(folder) / "benchmark.sqlite"
        with closing(connect(path)) as db:
            start(db, scenario())
            timings = []
            for _ in range(args.ticks):
                begin = perf_counter()
                final = advance(db, 1)
                timings.append((perf_counter() - begin) * 1000)
        print(json.dumps({
            "ticks": args.ticks, "cities": len(final["cities"]), "initial_population": 30_000,
            "population": sum(city["population"] for city in final["cities"].values()),
            "roads": len(final["roads"]), "shipments_in_transit": len(final["shipments"]),
            "median_ms": round(statistics.median(timings), 3),
            "max_ms": round(max(timings), 3), "sqlite_bytes": path.stat().st_size,
        }))


if __name__ == "__main__":
    main()
