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
            entity_id INTEGER NOT NULL, -- rename to subject_id
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
