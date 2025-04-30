import os
import re
import base64
import sys
import sqlite3
import unicodedata

conn = sqlite3.connect(os.environ.get("VERONIQUE_DB", "veronique.db"))
conn.row_factory = sqlite3.Row
orig_isolation_level, conn.isolation_level = conn.isolation_level, None

DATA_LABELS = [ROOT, LABEL, IS_A, VALID_FROM, VALID_UNTIL, AVATAR] = range(-1, -7, -1)


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

@migration(7)
def add_queries_table(cur):
    cur.execute("""
        CREATE TABLE queries (
            id INTEGER PRIMARY KEY,
            label VARCHAR(32) UNIQUE,
            sql TEXT
        )
    """)


def rebuild_search_index(cur):
    cur.execute("DELETE FROM search_index")
    for row in cur.execute("SELECT subject_id, value FROM claims WHERE verb_id = ?", (LABEL,)).fetchall():
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('claims', ?, ?)",
            (row["subject_id"], make_search_key(row["value"])),
        )
    for row in cur.execute("SELECT id, label FROM verbs").fetchall():
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('verbs', ?, ?)",
            (row["id"], make_search_key(row["label"])),
        )
    for row in cur.execute("SELECT id, label FROM queries").fetchall():
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('queries', ?, ?)",
            (row["id"], make_search_key(row["label"])),
        )


@migration(8)
def add_claims(cur):
    cur.execute("""
        CREATE TABLE verbs (
            id INTEGER PRIMARY KEY,
            label,
            data_type,  -- regular, plus "directed_link", "undirected_link"
            internal BOOL
        )
    """)
    cur.execute(f"""
        INSERT INTO verbs (
            id,
            label,
            data_type,
            internal
        ) VALUES (
            {ROOT},
            '',
            'directed_link',
            TRUE
        ), (
            {LABEL},
            'label',
            'string',
            TRUE
        ), (
            {IS_A},
            'category',
            'directed_link',
            TRUE
        ), (
            {VALID_FROM},
            'valid from',
            'date',
            TRUE
        ), (
            {VALID_UNTIL},
            'valid until',
            'date',
            TRUE
        ), (
            {AVATAR},
            'avatar',
            'picture',
            TRUE
        )
    """)
    prop_map = {}  # old->new
    for prop in cur.execute("SELECT * FROM properties").fetchall():
        refl_id = prop["reflected_property_id"]
        if refl_id == prop["id"]:
            # undirected
            data_type = "undirected_link"
        elif refl_id in prop_map:
            # we already processed the other side
            continue
        elif prop["data_type"] == "entity":
            data_type = "directed_link"
        else:
            data_type = prop["data_type"]
        cur.execute("""
                INSERT INTO verbs (
                    label,
                    data_type,
                    internal
                ) VALUES (
                    ?,
                    ?,
                    FALSE
                )
            """,
            (prop["label"], data_type),
        )
        prop_map[prop["id"]] = cur.lastrowid

    cur.execute("""
        CREATE TABLE claims (
            id INTEGER PRIMARY KEY,
            subject_id,
            verb_id,
            value,
            object_id,
            created_at TIMESTAMP DEFAULT (datetime('now')),
            updated_at TIMESTAMP DEFAULT (datetime('now'))
        )
    """)
    cat_map = {}  # old -> new
    for cat in cur.execute("SELECT * FROM categories").fetchall():
        cur.execute("INSERT INTO claims (verb_id) VALUES (?)", (ROOT,))
        cat_map[cat["id"]] = cur.lastrowid
        cur.execute(
            "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
            (cur.lastrowid, LABEL, cat["name"]),
        )

    entity_map = {}  # old -> new
    for entity in cur.execute("SELECT * FROM entities").fetchall():
        cur.execute(
            "INSERT INTO claims (verb_id) VALUES (?)",
            (ROOT,),
        )
        new_id = cur.lastrowid
        entity_map[entity["id"]] = new_id
        cur.execute(
            "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
            (new_id, LABEL, entity["name"]),
        )
        cur.execute(
            "INSERT INTO claims (subject_id, verb_id, object_id) VALUES (?, ?, ?)",
            (new_id, IS_A, cat_map[entity["category_id"]]),
        )
        if entity["has_avatar"]:
            with open(f"avatars/{entity['id']}.jpg", "rb") as f:
                body = f.read()
            cur.execute(
                "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
                (
                    new_id,
                    AVATAR,
                    f"data:image/jpeg;base64,{base64.b64encode(body).decode()}"
                ),
            )

    imported_facts = set()
    text_ref = re.compile(r"<@(\d+)>")
    for fact in cur.execute("SELECT * FROM facts").fetchall():
        if fact["object_id"]:
            if fact["property_id"] not in prop_map:
                # Skip loser of a directed relation (we deleted one half of
                # them earlier)
                continue
            if fact["reflected_fact_id"] in imported_facts:
                # Only import self-reflected facts (e.g. partner, friend) once
                continue
            cur.execute(
                "INSERT INTO claims (subject_id, verb_id, object_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (entity_map[fact["subject_id"]], prop_map[fact["property_id"]], entity_map[fact["object_id"]], fact["created_at"], fact["updated_at"]),
            )
            imported_facts.add(fact["id"])
        else:
            value = fact["value"]
            for ref_id in set(map(int, text_ref.findall(value))):
                value = value.replace(f"<@{ref_id}>", f"<@{entity_map[ref_id]}>")
            cur.execute(
                "INSERT INTO claims (subject_id, verb_id, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (entity_map[fact["subject_id"]], prop_map[fact["property_id"]], value, fact["created_at"], fact["updated_at"]),
            )
            imported_facts.add(fact["id"])
        new_id = cur.lastrowid
        if fact["valid_from"]:
            cur.execute(
                "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
                (new_id, VALID_FROM, fact["valid_from"]),
            )
        if fact["valid_until"]:
            cur.execute(
                "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
                (new_id, VALID_UNTIL, fact["valid_until"]),
            )

    cur.execute("""
        CREATE TABLE search_index (
            table_name TEXT,
            id INTEGER,
            value TEXT
        )
    """)
    rebuild_search_index(cur)

if os.environ.get("VERONIQUE_READONLY"):
    conn.execute("pragma query_only = ON;")

conn.isolation_level = orig_isolation_level
