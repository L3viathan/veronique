import sqlite3

conn = sqlite3.connect("veronique.db")

PAGE_SIZE = 20

ENCODERS = {
    "string": str,
    "number": str,
    "color": str,
    "date": str,
}

DECODERS = {
    "string": str,
    "creature": lambda _: None,
    "number": float,
    "color": str,
    "date": str,
}
SELF = object()

def setup_tables():
    cur = conn.cursor()
    cur.execute("CREATE TABLE creatures (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute(
        """
        CREATE TABLE properties
        (
            id INTEGER PRIMARY KEY,
            label VARCHAR(32) UNIQUE,
            type VARCHAR(32),
            reflected_property_id INTEGER,
            FOREIGN KEY(reflected_property_id) REFERENCES properties(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE facts
        (
            id INTEGER PRIMARY KEY,
            creature_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            value TEXT, -- for anything other than relations
            other_creature_id INTEGER,  -- for relations
            reflected_fact_id INTEGER,
            created_at TIMESTAMP DEFAULT (datetime('now')),  -- always UTC
            -- valid_from, valid_until
            FOREIGN KEY(creature_id) REFERENCES creatures(id),
            FOREIGN KEY(property_id) REFERENCES property(id)
            FOREIGN KEY(other_creature_id) REFERENCES creatures(id)
            FOREIGN KEY(reflected_fact_id) REFERENCES facts(id)
        )
        """
    )


def add_creature(name):
    cur = conn.cursor()
    cur.execute("INSERT INTO creatures (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def delete_creature(creature_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM creatures WHERE id = ?", (creature_id,))
    conn.commit()


def list_creatures(page=1):
    offset = (page - 1) * PAGE_SIZE
    cur = conn.cursor()
    return cur.execute(
        """
            SELECT
                c.id, c.name
            FROM creatures c
            LIMIT 20 OFFSET ?
        """,
        (offset,),
    ).fetchall()


def get_creature_facts(creature_id):
    cur = conn.cursor()
    facts = {}
    for fact_id, value, other_creature_id, created_at, label, type in cur.execute(
        """
            SELECT
                f.id,
                f.value,
                f.other_creature_id,
                f.created_at,
                p.label,
                p.type
            FROM facts f
            LEFT JOIN properties p ON f.property_id = p.id
            WHERE f.creature_id = ?
        """,
        (creature_id,),
    ).fetchall():
        facts.setdefault(label, []).append(
            {
                "fact_id": fact_id,
                "value": other_creature_id or DECODERS[type](value),
                "label": label,
                "type": type,
                "created_at": created_at,
            }
        )
    return facts


def get_creature_name(creature_id):
    cur = conn.cursor()
    rows = cur.execute(
        """
            SELECT name
            FROM creatures
            WHERE id = ?
        """,
        (creature_id,),
    ).fetchall()
    if rows:
        return rows[0][0]
    return None



def add_property(label, type, *, reflected_property_name=None):
    if reflected_property_name and type != "creature":
        raise ValueError("Reflexivity only makes sense with creatures.")
    cur = conn.cursor()
    cur.execute("INSERT INTO properties (label, type) VALUES (?, ?)", (label, type))
    first_property_id = cur.lastrowid
    if reflected_property_name:
        if reflected_property_name is SELF:
            cur.execute(
                "UPDATE properties SET reflected_property_id = ? WHERE id = ?",
                (first_property_id, first_property_id),
            )
        else:
            cur.execute(
                "INSERT INTO properties (label, type, reflected_property_id) VALUES (?, ?, ?)",
                (reflected_property_name, type, first_property_id),
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


def list_properties():
    cur = conn.cursor()
    return cur.execute(
        """
            SELECT
                id, label, type
            FROM properties
        """,
    ).fetchall()


def get_property(property_id):
    cur = conn.cursor()
    return cur.execute(
        """
            SELECT
                label, type
            FROM properties
            WHERE id = ?
        """,
        (property_id,),
    ).fetchone()


def add_fact(creature_id, property_id, value):
    cur = conn.cursor()
    [type, reflected_property_id] = cur.execute(
        "SELECT type, reflected_property_id FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()
    if type == "creature":
        cur.execute(
            """
                INSERT INTO facts
                    (creature_id, property_id, other_creature_id)
                VALUES
                    (?, ?, ?)
            """,
            (
                creature_id, property_id, value
            ),
        )
        first_fact_id = cur.lastrowid
        if reflected_property_id:
            cur.execute(
                """
                    INSERT INTO facts
                        (creature_id, property_id, other_creature_id, reflected_fact_id)
                    VALUES
                        (?, ?, ?, ?)
                """,
                (
                    value, reflected_property_id, creature_id, first_fact_id
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
        value = ENCODERS[type](value)
        cur.execute("""
            INSERT INTO facts
                (creature_id, property_id, value)
            VALUES
                (?, ?, ?)
            """,
            (
                creature_id, property_id, value
            ),
        )
        first_fact_id = cur.lastrowid
    conn.commit()
    return first_fact_id


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
    lover = add_property("in a relationship with", "creature", reflected_property_name=SELF)
    parent = add_property("parent of", "creature", reflected_property_name="child of")

    jonathan = add_creature("Jonathan")
    laura = add_creature("Laura")
    we_be_lovers = add_fact(laura, lover, jonathan)
