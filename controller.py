import sqlite3

conn = sqlite3.connect("veronique.db")

ENCODERS = {
    "string": str,
}

DECODERS = {
    "string": str,
}
SELF = object()

def setup_tables():
    cur = conn.cursor()
    cur.execute("CREATE TABLE creatures (id INTEGER PRIMARY KEY)")
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
            -- valid_from, valid_until
            FOREIGN KEY(creature_id) REFERENCES creatures(id),
            FOREIGN KEY(property_id) REFERENCES property(id)
            FOREIGN KEY(other_creature_id) REFERENCES creatures(id)
            FOREIGN KEY(reflected_fact_id) REFERENCES facts(id)
        )
        """
    )


def add_creature():
    cur = conn.cursor()
    cur.execute("INSERT INTO creatures DEFAULT VALUES")
    conn.commit()
    return cur.lastrowid


def delete_creature(creature_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM creatures WHERE id = ?", (creature_id,))
    conn.commit()


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


setup_tables()
lover = add_property("lover", "creature", reflected_property_name=SELF)
parent = add_property("parent", "creature", reflected_property_name="child")
name = add_property("name", "string")
# delete_property(1)
# delete_property(3)

jonathan = add_creature()
add_fact(jonathan, name, "Jonathan")
laura = add_creature()
add_fact(laura, name, "Laura")
we_be_lovers = add_fact(laura, lover, jonathan)

# delete_fact(we_be_lovers)

# example properties
# cur.lastrowid
# add_creature()
