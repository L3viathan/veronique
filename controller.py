import sqlite3

conn = sqlite3.connect("veronique.db")

ENCODERS = {
    "string": str,
}

DECODERS = {
    "string": str,
}

def setup_tables():
    cur = conn.cursor()
    cur.execute("CREATE TABLE creatures (id INTEGER PRIMARY KEY)")
    cur.execute(
        """
        CREATE TABLE properties
        (
            id INTEGER PRIMARY KEY,
            label VARCHAR(32),
            type VARCHAR(32),
            reflexivity INTEGER
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
            -- valid_from, valid_until
            FOREIGN KEY(creature_id) REFERENCES creatures(id),
            FOREIGN KEY(property_id) REFERENCES property(id)
            FOREIGN KEY(other_creature_id) REFERENCES creatures(id)
        )
        """
    )

def add_property(label, type, *, reflexivity=None):
    if reflexivity and type != "creature":
        raise ValueError("Reflexivity only makes sense with creatures.")
    cur = conn.cursor()
    cur.execute("INSERT INTO properties (label, type) VALUES (?, ?)", (label, type))
    first_property_id = cur.lastrowid
    if reflexivity:
        if reflexivity is True:  # self-reflexivity
            cur.execute(
                "UPDATE properties SET reflexivity = ? WHERE id = ?",
                (first_property_id, first_property_id),
            )
        else:
            cur.execute(
                "INSERT INTO properties (label, type, reflexivity) VALUES (?, ?, ?)",
                (reflexivity, type, first_property_id),
            )
            cur.execute(
                "UPDATE properties SET reflexivity = ? WHERE id = ?",
                (cur.lastrowid, first_property_id),
            )
    conn.commit()
    return first_property_id


def delete_property(property_id):
    cur = conn.cursor()
    [reflexivity] = cur.execute(
        "SELECT reflexivity FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()
    ids_to_delete = {property_id, reflexivity} - {None}
    for id_to_delete in ids_to_delete:
        cur.execute("DELETE FROM properties WHERE id = ?", (id_to_delete,))
    conn.commit()


def add_creature():
    cur = conn.cursor()
    cur.execute("INSERT INTO creatures DEFAULT VALUES")
    conn.commit()
    return cur.lastrowid


def delete_creature(creature_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM creatures WHERE id = ?", (creature_id,))
    conn.commit()


def add_fact(creature_id, property_id, value):
    cur = conn.cursor()
    [type, reflexivity] = cur.execute(
        "SELECT type, reflexivity FROM properties WHERE id = ?",
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
        if reflexivity:
            # ISSUE: what if you have several relations with the same triple?
            # What do you do when deleting? It doesn't seem to matter at the
            # moment (where we have no additional columns), just delete one
            # (need to ensure that!) When we add more stuff (e.g. valid_from)
            # we need to make sure to always change one matching other fact.
            # Or maybe we need to link the facts to eachother, similar to how
            # the properties have that reflexivity column...
            cur.execute(
                """
                    INSERT INTO facts
                        (creature_id, property_id, other_creature_id)
                    VALUES
                        (?, ?, ?)
                """,
                (
                    value, reflexivity, creature_id
                ),
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
    conn.commit()


setup_tables()
lover = add_property("lover", "creature", reflexivity=True)
parent = add_property("parent", "creature", reflexivity="child")
name = add_property("name", "string")
# delete_property(1)
# delete_property(3)

jonathan = add_creature()
add_fact(jonathan, name, "Jonathan")
laura = add_creature()
add_fact(laura, name, "Laura")
add_fact(laura, lover, jonathan)

# example properties
# cur.lastrowid
# add_creature()
