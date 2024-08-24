import sqlite3
from property_types import TYPES, entity

conn = sqlite3.connect("veronique.db")
conn.row_factory = sqlite3.Row

SELF = object()
class lazy:
    unset = object()
    def __init__(self, name):
        self.value = lazy.unset
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if getattr(instance, f"_{self.name}", lazy.unset) is lazy.unset:
            +instance
        return getattr(instance, f"_{self.name}")

    def __set__(self, instance, value):
        setattr(instance, f"_{self.name}", value)


class Model:
    # core assumptions: everything is immutable, we can only add rows
    def __new__(cls, id):
        if id in cls._cache:
            return cls._cache[id]
        obj = super(Model, cls).__new__(cls)
        cls._cache[id] = obj
        obj._populated = False
        return obj

    def __init__(self, id):
        self.id = id

    def __pos__(self):
        if not self._populated:
            self._populated = True
            self.populate()
        return self

    def __repr__(self):
        return f"<{type(self).__name__} id={self.id}{'+' if self._populated else '-'}>"

    def __init_subclass__(cls):
        cls._cache = {}
        for field in cls.fields:
            setattr(cls, field, lazy(field))

    @classmethod
    def all(cls):
        # FIXME: do this smarter, plus pagination
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            """
        ).fetchall():
            yield cls(row["id"])


class EntityType(Model):
    table_name = "entity_types"
    fields = ("name",)
    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
                SELECT
                    id, name
                FROM entity_types
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No EntityType with this ID found")
        self.name = row["name"]

    @classmethod
    def new(cls, name):
        cur = conn.cursor()
        cur.execute("INSERT INTO entity_types (name) VALUES (?)", (name,))
        conn.commit()
        return cls(cur.lastrowid)

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE entity_types
            SET name=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        conn.commit()
        self.name = name

    def __format__(self, fmt):
        if fmt == "rename-form":
            return f'<input name="name" value="{self.name}" hx-post="/entity-types/{self.id}/rename" hx-swap="outerHTML">'
        elif fmt == "heading":
            return f'<h2 hx-get="/entity-types/{self.id}/rename" hx-swap="outerHTML">{self.name}</h2>'
        else:
            return f"""<a
                class="clickable entity-type"
                hx-push-url="true"
                hx-get="/entity-types/{self.id}"
                hx-select="#container"
                hx-target="#container"
            >{self.name}</a>"""

    def __str__(self):
        return f"{self}"


class Entity(Model):
    fields = ("name", "entity_type")
    table_name = "entities"
    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
                SELECT name, entity_type_id
                FROM entities
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Entity with this ID found")
        self.name = row["name"]
        self.entity_type = EntityType(row["entity_type_id"])

    @classmethod
    def new(cls, name, entity_type):
        cur = conn.cursor()
        cur.execute("INSERT INTO entities (name, entity_type_id) VALUES (?, ?)", (name, entity_type.id))
        conn.commit()
        return Entity(cur.lastrowid)

    @classmethod
    def all(cls, entity_type=None):
        # FIXME: do this smarter, plus pagination
        conditions = ["1=1"]
        values = []
        if entity_type is not None:
            conditions.append(f"entity_type_id = ?")
            values.append(entity_type.id)

        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            WHERE {" AND ".join(conditions)}
            """,
            tuple(values),
        ).fetchall():
            yield cls(row["id"])

    def __format__(self, fmt):
        if fmt == "rename-form":
            return f'<input name="name" value="{self.name}" hx-post="/entities/{self.id}/rename" hx-swap="outerHTML">'
        elif fmt == "heading":
            return f'<h2 hx-get="/entities/{self.id}/rename" hx-swap="outerHTML">{self.name}</h2>'
        elif fmt == "full":
            return f'<a class="clickable entity-link" hx-push-url="true" hx-select="#container" hx-target="#container" hx-get="/entities/{self.id}">{self.name}</a> ({self.entity_type})'
        else:
            return f'<a class="clickable entity-link" hx-push-url="true" hx-select="#container" hx-target="#container" hx-get="/entities/{self.id}">{self.name}</a>'

    def __str__(self):
        return f"{self}"

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE entities
            SET name=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        conn.commit()
        self.name = name

    @property
    def facts(self):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM facts
            WHERE entity_id = ?
            """,
            (self.id,),
        ).fetchall():
            yield Fact(row["id"])

    @property
    def incoming_facts(self):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                f.id
            FROM facts f
            LEFT JOIN properties p
            ON f.property_id = p.id
            WHERE f.other_entity_id = ? AND (p.reflected_property_id IS NULL OR p.reflected_property_id <> p.id)
            """,
            (self.id,),
        ).fetchall():
            yield Fact(row["id"])


class Property(Model):
    fields = ("label", "data_type", "extra_data", "subject_type", "object_type", "reflected_property")
    table_name = "properties"
    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                label,
                data_type,
                extra_data,
                subject_type_id,
                object_type_id,
                reflected_property_id
            FROM properties
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Property with this ID found")
        self.label = row["label"]
        self.data_type = TYPES[row["data_type"]]
        self.extra_data = row["extra_data"]
        self.subject_type = EntityType(row["subject_type_id"])
        if row["object_type_id"]:
            # relation to an entity
            self.object_type = EntityType(row["object_type_id"])
        else:
            self.object_type = None
        if row["reflected_property_id"]:
            self.reflected_property = Property(row["reflected_property_id"])
        else:
            self.reflected_property = None

    @classmethod
    def new(cls, label, *, data_type, subject_type, reflected_property_name=None, object_type=None, extra_data=None):
        if reflected_property_name and data_type.name != "entity":
            raise ValueError(f"Reflexivity only makes sense with entities, not with {data_type}.")
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO
                properties
                (
                    label,
                    data_type,
                    extra_data,
                    subject_type_id,
                    object_type_id
                ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                label,
                data_type.name,
                extra_data,
                subject_type.id,
                object_type and object_type.id,
            ),
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
                    (reflected_property_name, data_type.name, first_property_id, object_type.id, subject_type.id),
                )
                cur.execute(
                    "UPDATE properties SET reflected_property_id = ? WHERE id = ?",
                    (cur.lastrowid, first_property_id),
                )
        conn.commit()
        return Property(first_property_id)

    @property
    def facts(self):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM facts
            WHERE property_id = ?
            """,
            (self.id,),
        ).fetchall():
            yield Fact(row["id"])

    @classmethod
    def all(cls, subject_type=None, object_type=None):
        # FIXME: do this smarter, plus pagination
        conditions = ["1=1"]
        values = []
        if subject_type is not None:
            conditions.append(f"subject_type_id = ?")
            values.append(subject_type.id)
        if object_type is not None:
            conditions.append(f"object_type_id = ?")
            values.append(object_type.id)

        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            WHERE {" AND ".join(conditions)}
            """,
            tuple(values),
        ).fetchall():
            yield cls(row["id"])

    def __format__(self, fmt):
        if fmt == "full":
            arrow = (
                "" if self.object_type is None  # not a entity-entity link
                else "⭢" if self.reflected_property is None
                else "⮂" if self.reflected_property.id != self.id
                else "⭤"
            )
            return f"""<a
                class="clickable property"
                hx-push-url="true"
                hx-get="/properties/{self.id}"
                hx-select="#container"
                hx-target="#container"
            >{self.subject_type} {self.label} {self.object_type or self.data_type}{arrow}</a>"""
        else:
            return f"""<a
                class="clickable property"
                hx-get="/properties/{self.id}"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
            >{self.label}</a>"""

    def __str__(self):
        return f"{self}"


class Fact(Model):
    fields = ("subj", "prop", "obj", "reflected_fact", "created_at")
    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                entity_id,
                property_id,
                value,
                other_entity_id,
                reflected_fact_id,
                created_at
            FROM
                facts
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Fact with this ID found")
        self.subj = Entity(row["entity_id"])
        self.prop = Property(row["property_id"])
        if row["other_entity_id"]:
            self.obj = Entity(row["other_entity_id"])
        else:
            self.obj = Plain.decode(self.prop.data_type, row["value"])
        if row["reflected_fact_id"]:
            self.reflected_fact = +Fact(row["reflected_fact_id"])
        else:
            self.reflected_fact = None
        self.created_at = row["created_at"]

    @classmethod
    def new(cls, entity, prop, value):
        cur = conn.cursor()
        if prop.data_type.name == "entity":
            cur.execute(
                """
                    INSERT INTO facts
                        (entity_id, property_id, other_entity_id)
                    VALUES
                        (?, ?, ?)
                """,
                (
                    entity.id, prop.id, value.id
                ),
            )
            first_fact_id = cur.lastrowid
            if prop.reflected_property:
                cur.execute(
                    """
                        INSERT INTO facts
                            (entity_id, property_id, other_entity_id, reflected_fact_id)
                        VALUES
                            (?, ?, ?, ?)
                    """,
                    (
                        value.id, prop.reflected_property.id, entity.id, first_fact_id
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
            cur.execute("""
                INSERT INTO facts
                    (entity_id, property_id, value)
                VALUES
                    (?, ?, ?)
                """,
                (
                    entity.id, prop.id, value.encode()
                ),
            )
            first_fact_id = cur.lastrowid
        conn.commit()
        return Fact(first_fact_id)

    def __format__(self, fmt):
        if fmt == "short":
            return f"""<span class="vp">
                {self.prop}
                {self.obj}
            </span>
            <span class="hovercreated" style="font-size: xx-small;">created {self.created_at}</span>
            """
        else:
            return f"""<span class="fact">
                {self.subj}
                <span class="vp">
                    {self.prop}
                    {self.obj}
                </span>
            </span>
            <span class="hovercreated" style="font-size: xx-small;">created {self.created_at}</span>
            """

    def __str__(self):
        return f"{self}"


class Plain:
    def __init__(self, value, data_type):
        self.data_type = data_type
        self.value = value

    @classmethod
    def decode(cls, data_type, value):
        return Plain(data_type.decode(value), data_type)

    def encode(self):
        return self.data_type.encode(self.value)

    def __str__(self):
        return self.data_type.display_html(self.value)
