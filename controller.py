from datetime import datetime
import sqlite3

conn = sqlite3.connect("veronique.db")
conn.row_factory = sqlite3.Row

PAGE_SIZE = 20

def float_int(val):
    val = float(val)
    if val.is_integer():
        val = int(val)
    return val

ENCODERS = {
    "string": str,
    "number": str,
    "color": str,
    "date": str,
    "boolean": lambda v: v or "off",
    "enum": str,
    "age": str,
}

DECODERS = {
    "string": str,
    "entity": lambda _: None,
    "number": float_int,
    "color": str,
    "date": str,
    "boolean": "on".__eq__,
    "enum": str,
    "age": float_int,
}
SELF = object()

def setup_tables():
    cur = conn.cursor()
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
            subject_type_id INTEGER,
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
            entity_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            value TEXT, -- for anything other than relations
            other_entity_id INTEGER,  -- for relations
            reflected_fact_id INTEGER,
            created_at TIMESTAMP DEFAULT (datetime('now')),  -- always UTC
            -- valid_from, valid_until
            FOREIGN KEY(entity_id) REFERENCES entities(id),
            FOREIGN KEY(property_id) REFERENCES property(id)
            FOREIGN KEY(other_entity_id) REFERENCES entities(id)
            FOREIGN KEY(reflected_fact_id) REFERENCES facts(id)
        )
        """
    )


def add_entity_type(name):
    cur = conn.cursor()
    cur.execute("INSERT INTO entity_types (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def list_entity_types():
    cur = conn.cursor()
    return cur.execute(
        """
            SELECT
                id, name
            FROM entity_types
        """,
    ).fetchall()


def add_entity(name, entity_type_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO entities (name, entity_type_id) VALUES (?, ?)", (name, entity_type_id))
    conn.commit()
    return cur.lastrowid


def delete_entity(entity_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.commit()


def list_entities(page=1, entity_type_id=None):
    offset = (page - 1) * PAGE_SIZE
    cur = conn.cursor()
    condition = ""
    values = []
    if entity_type_id is not None:
        condition = "WHERE entity_type_id = ?"
        values.append(entity_type_id)
    values.append(offset)
    query = f"""
        SELECT
            c.id, c.name, c.entity_type_id
        FROM entities c
        {condition}
        LIMIT 20 OFFSET ?
    """
    return cur.execute(
        query,
        tuple(values),
    ).fetchall()


def get_entity_facts(entity_id):
    cur = conn.cursor()
    facts = {}
    for fact_id, value, other_entity_id, created_at, label, data_type in cur.execute(
        """
            SELECT
                f.id,
                f.value,
                f.other_entity_id,
                f.created_at,
                p.label,
                p.data_type
            FROM facts f
            LEFT JOIN properties p ON f.property_id = p.id
            WHERE f.entity_id = ?
        """,
        (entity_id,),
    ).fetchall():
        facts.setdefault(label, []).append(
            {
                "fact_id": fact_id,
                "value": other_entity_id or DECODERS[data_type](value),
                "label": label,
                "data_type": data_type,
                "created_at": datetime.fromisoformat(created_at),
            }
        )
    return facts


def get_entity(entity_id):
    cur = conn.cursor()
    rows = cur.execute(
        """
            SELECT name, entity_type_id
            FROM entities
            WHERE id = ?
        """,
        (entity_id,),
    ).fetchall()
    if rows:
        return rows[0]
    return None



def add_property(
    label,
    data_type,
    subject_type_id=None,
    *,
    object_type_id=None,
    reflected_property_name=None,
    extra_data=None,
):
    if reflected_property_name and data_type != "entity":
        raise ValueError("Reflexivity only makes sense with entities.")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO properties (label, data_type, extra_data, subject_type_id, object_type_id) VALUES (?, ?, ?, ?, ?)",
        (label, data_type, extra_data, subject_type_id, object_type_id),
    )
    first_property_id = cur.lastrowid
    if reflected_property_name:
        if reflected_property_name is SELF:
            cur.execute(
                "UPDATE properties SET reflected_property_id = ? WHERE id = ?",
                (first_property_id, first_property_id),
            )
        else:
            cur.execute(
                "INSERT INTO properties (label, data_type, reflected_property_id, subject_type_id, object_type_id) VALUES (?, ?, ?, ?, ?)",
                (reflected_property_name, data_type, first_property_id, object_type_id, subject_type_id),
            )
            cur.execute(
                "UPDATE properties SET reflected_property_id = ? WHERE id = ?",
                (cur.lastrowid, first_property_id),
            )
    conn.commit()
    return first_property_id


def delete_property(property_id):
    cur = conn.cursor()
    [reflected_property_id] = cur.execute(
        "SELECT reflected_property_id FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()
    for id_to_delete in {property_id, reflected_property_id} - {None}:
        cur.execute("DELETE FROM properties WHERE id = ?", (id_to_delete,))
    conn.commit()


def list_properties(subject_type_id=None, object_type_id=None):
    cur = conn.cursor()
    conditions = ["1=1"]
    values = []
    if subject_type_id is not None:
        conditions.append(f"subject_type_id = ?")
        values.append(subject_type_id)
    if object_type_id is not None:
        conditions.append(f"object_type_id = ?")
        values.append(object_type_id)
    return cur.execute(
        f"""
            SELECT
                id, label, data_type, subject_type_id, object_type_id
            FROM properties
            WHERE {" AND ".join(conditions)}
        """,
        tuple(values),
    ).fetchall()


def get_property(property_id):
    cur = conn.cursor()
    return cur.execute(
        """
            SELECT
                label, data_type, extra_data, subject_type_id, object_type_id
            FROM properties
            WHERE id = ?
        """,
        (property_id,),
    ).fetchone()


def add_fact(entity_id, property_id, value):
    cur = conn.cursor()
    [data_type, reflected_property_id] = cur.execute(
        "SELECT data_type, reflected_property_id FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()
    if data_type == "entity":
        cur.execute(
            """
                INSERT INTO facts
                    (entity_id, property_id, other_entity_id)
                VALUES
                    (?, ?, ?)
            """,
            (
                entity_id, property_id, value
            ),
        )
        first_fact_id = cur.lastrowid
        if reflected_property_id:
            cur.execute(
                """
                    INSERT INTO facts
                        (entity_id, property_id, other_entity_id, reflected_fact_id)
                    VALUES
                        (?, ?, ?, ?)
                """,
                (
                    value, reflected_property_id, entity_id, first_fact_id
                ),
            )
            cur.execute(
                """
                    UPDATE facts
                    SET reflected_fact_id = ?
                    WHERE id = ?
                """,
                (cur.lastrowid, first_fact_id),
            )
    else:
        value = ENCODERS[data_type](value)
        cur.execute("""
            INSERT INTO facts
                (entity_id, property_id, value)
            VALUES
                (?, ?, ?)
            """,
            (
                entity_id, property_id, value
            ),
        )
        first_fact_id = cur.lastrowid
    conn.commit()
    return first_fact_id


def get_fact(fact_id):
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT
            f.value AS value,
            f.entity_id AS entity_id,
            p.label AS label,
            p.data_type AS data_type
        FROM facts f
        LEFT JOIN properties p ON f.property_id = p.id
        WHERE f.id = ?
        """,
        (fact_id,)
    ).fetchone()
    return row


def delete_fact(fact_id):
    cur = conn.cursor()
    [reflected_fact_id] = cur.execute(
        "SELECT reflected_fact_id FROM facts WHERE id = ?",
        (fact_id,)
    ).fetchone()
    for id_to_delete in {fact_id, reflected_fact_id} - {None}:
        cur.execute("DELETE FROM facts WHERE id = ?", (id_to_delete,))
    conn.commit()


if __name__ == "__main__":
    setup_tables()
    human = add_entity_type("human")
    married = add_property("married to", "entity", subject_type_id=human, object_type_id=human, reflected_property_name=SELF)
    parent = add_property("parent of", "entity", subject_type_id=human, object_type_id=human, reflected_property_name="child of")
    haircolor = add_property("haircolor", "color", subject_type_id=human)
    birthday = add_property("birthday", "date", subject_type_id=human)
    nickname = add_property("nickname", "string", subject_type_id=human)

    jonathan = add_entity("Jonathan", human)
    laura = add_entity("Laura", human)
    david = add_entity("David", human)
    add_fact(laura, parent, david)
    add_fact(jonathan, parent, david)
    add_fact(laura, married, jonathan)
    add_fact(laura, haircolor, "#2889be")
    add_fact(laura, birthday, "1991-03-29")
    add_fact(laura, nickname, "sarnthil")
