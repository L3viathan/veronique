import os
import sys
import sqlite3

conn = sqlite3.connect(os.environ.get("VERONIQUE_DB", "veronique.db"))
conn.row_factory = sqlite3.Row


try:
    cur = conn.cursor()
    row = cur.execute("SELECT version FROM state").fetchone()
    version = row["version"]
except sqlite3.OperationalError:
    version = 0
cur.close()


def migration(number):
    def deco(fn):
        global version
        if number >= version:
            print("Running migration", fn.__name__)
            try:
                cur = conn.cursor()
                fn(cur)
                cur.execute("UPDATE state SET version = ?", (version + 1,))
                conn.commit()
                print("Migration successful")
                version += 1
            except sqlite3.OperationalError as e:
                print("Rolling back migration:", e)
                conn.rollback()
                sys.exit(1)
            cur.close()
    return deco


@migration(0)
def initial(cur):
    cur.execute("""
        CREATE TABLE state (version INTEGER)
        """
    )
    cur.execute("""
        INSERT INTO state (version) VALUES (0)
        """
    )
    cur.execute("""
        CREATE TABLE entity_types
        (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE entities
        (
            id INTEGER PRIMARY KEY,
            name TEXT,
            entity_type_id INTEGER NOT NULL,
            FOREIGN KEY(entity_type_id) REFERENCES entity_types(id)
        )
    """)
    cur.execute(
        """
        CREATE TABLE properties
        (
            id INTEGER PRIMARY KEY,
            label VARCHAR(32) UNIQUE,
            data_type VARCHAR(32),
            reflected_property_id INTEGER,
            extra_data TEXT,
            subject_type_id INTEGER NOT NULL,
            object_type_id INTEGER,
            FOREIGN KEY(reflected_property_id) REFERENCES properties(id),
            FOREIGN KEY(subject_type_id) REFERENCES entity_types(id),
            FOREIGN KEY(object_type_id) REFERENCES entity_types(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE facts
        (
            id INTEGER PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            value TEXT, -- for anything other than relations
            object_id INTEGER,  -- for relations
            reflected_fact_id INTEGER,
            created_at TIMESTAMP DEFAULT (datetime('now')),  -- always UTC
            FOREIGN KEY(subject_id) REFERENCES entities(id),
            FOREIGN KEY(property_id) REFERENCES property(id)
            FOREIGN KEY(object_id) REFERENCES entities(id)
            FOREIGN KEY(reflected_fact_id) REFERENCES facts(id)
        )
        """
    )


@migration(1)
def add_updated_at(cur):
    cur.execute(
        """
        ALTER TABLE facts
        ADD updated_at TIMESTAMP
        """
    )


@migration(2)
def add_validity(cur):
    cur.execute(
        """
        ALTER TABLE facts
        ADD valid_from VARCHAR(10)
        """
    )
    cur.execute(
        """
        ALTER TABLE facts
        ADD valid_until VARCHAR(10)
        """
    )


@migration(3)
def add_has_avatar(cur):
    cur.execute(
        """
        ALTER TABLE entities
        ADD has_avatar INT NOT NULL DEFAULT 0
        """
    )

if os.environ.get("VERONIQUE_READONLY"):
    conn.execute("pragma query_only = ON;")
