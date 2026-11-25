"""Atomic SQLite checkpoints and the per-tick event log."""
import json
import sqlite3

from .scenario import MODEL_VERSION, initialize
from .simulation import Simulation


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
