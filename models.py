"""
Data models for the Smart Disaster Relief Resource Management System.
Uses Python's built-in sqlite3 – no external ORM needed.
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "disaster_relief.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS camps (
                camp_id                INTEGER PRIMARY KEY AUTOINCREMENT,
                location               TEXT    NOT NULL,
                max_capacity           INTEGER NOT NULL,
                available_food         INTEGER NOT NULL DEFAULT 0,
                available_medical_kits INTEGER NOT NULL DEFAULT 0,
                volunteers             INTEGER NOT NULL DEFAULT 0,
                current_occupancy      INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS victims (
                victim_id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name                     TEXT    NOT NULL,
                age                      INTEGER NOT NULL,
                health_condition         TEXT    NOT NULL DEFAULT 'normal',
                assigned_camp_id         INTEGER REFERENCES camps(camp_id),
                food_distributed         INTEGER NOT NULL DEFAULT 0,
                medical_kits_distributed INTEGER NOT NULL DEFAULT 0
            );
        """)


# ── Camp helpers ──────────────────────────────────────────────────────────────

class Camp:
    def __init__(self, row):
        self._row = row

    def __getattr__(self, name):
        try:
            return self._row[name]
        except (IndexError, KeyError):
            raise AttributeError(name)

    @property
    def is_full(self):
        return self.current_occupancy >= self.max_capacity

    @property
    def occupancy_percentage(self):
        if self.max_capacity == 0:
            return 0
        return round((self.current_occupancy / self.max_capacity) * 100, 1)


def get_all_camps():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM camps ORDER BY camp_id").fetchall()
    return [Camp(r) for r in rows]


def get_camp(camp_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM camps WHERE camp_id=?", (camp_id,)).fetchone()
    return Camp(row) if row else None


def get_available_camps():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM camps WHERE current_occupancy < max_capacity ORDER BY camp_id"
        ).fetchall()
    return [Camp(r) for r in rows]


def create_camp(location, max_capacity, available_food, available_medical_kits, volunteers):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO camps (location,max_capacity,available_food,available_medical_kits,volunteers) VALUES (?,?,?,?,?)",
            (location, max_capacity, available_food, available_medical_kits, volunteers),
        )
        return cur.lastrowid


def update_camp_resources(camp_id, food_delta=0, kits_delta=0, occupancy_delta=0):
    with get_db() as conn:
        conn.execute(
            "UPDATE camps SET available_food=available_food+?, available_medical_kits=available_medical_kits+?, current_occupancy=current_occupancy+? WHERE camp_id=?",
            (food_delta, kits_delta, occupancy_delta, camp_id),
        )


# ── Victim helpers ────────────────────────────────────────────────────────────

class Victim:
    def __init__(self, row):
        self._row = row

    def __getattr__(self, name):
        try:
            return self._row[name]
        except (IndexError, KeyError):
            raise AttributeError(name)

    @property
    def is_critical(self):
        return self.health_condition == "critical"


def get_all_victims():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM victims ORDER BY victim_id").fetchall()
    return [Victim(r) for r in rows]


def get_victim(victim_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM victims WHERE victim_id=?", (victim_id,)).fetchone()
    return Victim(row) if row else None


def get_victims_for_camp(camp_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM victims WHERE assigned_camp_id=? ORDER BY victim_id", (camp_id,)
        ).fetchall()
    return [Victim(r) for r in rows]


def create_victim(name, age, health_condition, camp_id):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO victims (name,age,health_condition,assigned_camp_id) VALUES (?,?,?,?)",
            (name, age, health_condition, camp_id),
        )
        return cur.lastrowid


def update_victim_distributions(victim_id, food_delta=0, kits_delta=0):
    with get_db() as conn:
        conn.execute(
            "UPDATE victims SET food_distributed=food_distributed+?, medical_kits_distributed=medical_kits_distributed+? WHERE victim_id=?",
            (food_delta, kits_delta, victim_id),
        )
