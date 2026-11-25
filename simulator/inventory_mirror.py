"""Persist inventory observed on the dedicated ASA trial server."""
import sqlite3


class InventoryMirror:
    def __init__(self, connection, structure_id):
        if type(structure_id) is not int or not 0 < structure_id < 2**32:
            raise ValueError("Invalid trial structure ID")
        self.connection = connection
        self.structure_id = structure_id
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS inventory_current (
                structure_id INTEGER PRIMARY KEY, boot_id TEXT NOT NULL,
                seq INTEGER NOT NULL, wood INTEGER NOT NULL CHECK (wood >= 0)
            );
            CREATE TABLE IF NOT EXISTS inventory_boots (
                structure_id INTEGER NOT NULL, boot_id TEXT NOT NULL,
                PRIMARY KEY (structure_id, boot_id)
            );
        """)

    def observe(self, boot_id, seq, inventory):
        if (not isinstance(inventory, dict)
                or type(inventory.get("structure_id")) is not int
                or inventory["structure_id"] != self.structure_id
                or type(inventory.get("wood")) is not int
                or not 0 <= inventory["wood"] <= 2**31 - 1):
            raise ValueError("Unexpected inventory structure or quantity")
        row = (boot_id, seq, inventory["wood"])
        db = self.connection
        with db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT boot_id, seq, wood FROM inventory_current WHERE structure_id = ?",
                (self.structure_id,),
            ).fetchone()
            if current and current[0] == boot_id:
                if seq < current[1] or (seq == current[1] and row != current):
                    raise ValueError("Stale or conflicting inventory observation")
                if row == current:
                    return
            else:
                inserted = db.execute(
                    "INSERT OR IGNORE INTO inventory_boots VALUES (?, ?)", (self.structure_id, boot_id)
                )
                if not inserted.rowcount:
                    raise ValueError("Retired inventory boot")
            db.execute("""
                INSERT INTO inventory_current VALUES (?, ?, ?, ?)
                ON CONFLICT (structure_id) DO UPDATE
                SET boot_id = excluded.boot_id, seq = excluded.seq, wood = excluded.wood
            """, (self.structure_id, *row))

    def resume(self, boot_id):
        current = self.connection.execute(
            "SELECT seq FROM inventory_current WHERE structure_id = ? AND boot_id = ?",
            (self.structure_id, boot_id),
        ).fetchone()
        if current:
            return current[0]
        if self.connection.execute(
            "SELECT 1 FROM inventory_boots WHERE structure_id = ? AND boot_id = ?",
            (self.structure_id, boot_id),
        ).fetchone():
            raise ValueError("Retired inventory boot")
        return 0


def open_mirror(path, structure_id):
    return InventoryMirror(sqlite3.connect(path), structure_id)
