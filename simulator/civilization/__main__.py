"""Run the standalone civilization simulation on a finite grid."""
import argparse
from contextlib import closing
import json
from pathlib import Path

from .storage import advance, connect, start


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
