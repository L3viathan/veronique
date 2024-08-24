import sys
import objects as O


def setup_tables():
    cur = O.conn.cursor()
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
    if any(p in sys.argv for p in ("-h", "-?", "--help")):
        print("Creates the necessary tables in veronique.db\nUsage: db-setup.py [--add-example-data]")
        sys.exit(0)
    setup_tables()
    if "--add-example-data" in sys.argv:
        from property_types import TYPES

        human = O.EntityType.new("human")
        married = O.Property.new(
            "married to",
            data_type=TYPES["entity"],
            subject_type=human,
            object_type=human,
            reflected_property_name=O.SELF,
        )
        parent = O.Property.new(
            "parent of",
            data_type=TYPES["entity"],
            subject_type=human,
            object_type=human,
            reflected_property_name="child of",
        )
        haircolor = O.Property.new("haircolor", TYPES["color"], subject_type=human)
        birthday = O.Property.new("birthday", TYPES["date"], subject_type=human)
        nickname = O.Property.new("nickname", TYPES["string"], subject_type=human)

        jonathan = O.Entity.new("Jonathan", human)
        laura = O.Entity.new("Laura", human)
        david = O.Entity.new("David", human)

        O.Fact.new(laura, parent, david)
        O.Fact.new(jonathan, parent, david)
        O.Fact.new(laura, married, jonathan)
        O.Fact.new(laura, haircolor, Plain("#2889be", TYPES["color"]))
        O.Fact.new(laura, birthday, Plain("1991-03-29", TYPES["date"]))
        O.Fact.new(laura, nickname, Plain("sarnthil", TYPES["string"]))
