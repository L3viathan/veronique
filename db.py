import os
import sys
import sqlite3
import unicodedata

conn = sqlite3.connect(os.environ.get("VERONIQUE_DB", "veronique.db"))
conn.row_factory = sqlite3.Row
orig_isolation_level, conn.isolation_level = conn.isolation_level, None


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
                cur.execute("BEGIN")
                fn(cur)
                cur.execute("UPDATE state SET version = ?", (version + 1,))
                cur.execute("COMMIT")
                print("Migration successful")
                version += 1
            except sqlite3.OperationalError as e:
                print("Rolling back migration:", e)
                cur.execute("ROLLBACK")
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


def make_search_key(name):
    word = []
    words = []
    for char in unicodedata.normalize("NFKD", name):
        cat = unicodedata.category(char)[0]
        if cat == "L":  # letters
            word.append(char)
        elif cat in "ZP" and word:
            # whitespace, punctuation
            words.append("".join(word))
            word = []
        elif cat == "M":
            # modifier: ignore
            continue
    if word:
        words.append("".join(word))
    return " ".join(words).casefold()


@migration(4)
def add_search_key(cur):
    cur.execute(
        """
        ALTER TABLE entities
        ADD search_key TEXT
        """
    )
    cur.execute("SELECT id, name FROM entities")
    rows = cur.fetchall()
    cur.executemany(
        "UPDATE entities SET search_key=? WHERE id=?",
        ((make_search_key(name), id) for id, name in rows)
    )

@migration(5)
def rename_entity_type_to_category(cur):
    cur.execute("ALTER TABLE entity_types RENAME TO categories")
    cur.execute("ALTER TABLE entities RENAME COLUMN entity_type_id TO category_id")
    cur.execute("ALTER TABLE properties RENAME COLUMN subject_type_id TO subject_category_id")
    cur.execute("ALTER TABLE properties RENAME COLUMN object_type_id TO object_category_id")


@migration(6)
def remove_constraints(cur):
    # These constraints do more harm than good, since they're not enforced
    # They also refer to the wrong table names now.
    cur.execute("""
        CREATE TABLE properties_tmp (
            id INTEGER PRIMARY KEY,
            label VARCHAR(32) UNIQUE,
            data_type VARCHAR(32),
            reflected_property_id INTEGER,
            extra_data TEXT,
            subject_category_id INTEGER NOT NULL,
            object_category_id INTEGER
        )
    """)
    cur.execute("""
        INSERT INTO properties_tmp (
            id,
            label,
            data_type,
            reflected_property_id,
            extra_data,
            subject_category_id,
            object_category_id
        ) SELECT
            id,
            label,
            data_type,
            reflected_property_id,
            extra_data,
            subject_category_id,
            object_category_id
        FROM properties
    """)
    cur.execute("""
        DROP TABLE properties
    """)
    cur.execute("""
        ALTER TABLE properties_tmp RENAME TO properties
    """)
    cur.execute("""
        CREATE TABLE entities_tmp (
            id INTEGER PRIMARY KEY,
            name TEXT,
            category_id INTEGER NOT NULL,
            has_avatar INT NOT NULL DEFAULT 0,
            search_key TEXT
        )
    """)
    cur.execute("""
        INSERT INTO entities_tmp (
            id,
            name,
            category_id,
            has_avatar,
            search_key
        ) SELECT
            id,
            name,
            category_id,
            has_avatar,
            search_key
        FROM entities
    """)
    cur.execute("""
        DROP TABLE entities
    """)
    cur.execute("""
        ALTER TABLE entities_tmp RENAME TO entities
    """)
    cur.execute("""
        CREATE TABLE facts_tmp (
            id INTEGER PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            value TEXT, -- for anything other than relations
            object_id INTEGER,  -- for relations
            reflected_fact_id INTEGER,
            created_at TIMESTAMP DEFAULT (datetime('now')),
            updated_at TIMESTAMP,
            valid_from VARCHAR(10),
            valid_until VARCHAR(10)
        )
    """)
    cur.execute("""
        INSERT INTO facts_tmp (
            id,
            subject_id,
            property_id,
            value,
            object_id,
            reflected_fact_id,
            created_at,
            updated_at,
            valid_from,
            valid_until
        ) SELECT
            id,
            subject_id,
            property_id,
            value,
            object_id,
            reflected_fact_id,
            created_at,
            updated_at,
            valid_from,
            valid_until
        FROM facts
    """)
    cur.execute("""
        DROP TABLE facts
    """)
    cur.execute("""
        ALTER TABLE facts_tmp RENAME TO facts
    """)

if os.environ.get("VERONIQUE_READONLY"):
    conn.execute("pragma query_only = ON;")

conn.isolation_level = orig_isolation_level
