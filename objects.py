import re
from datetime import date, datetime

from property_types import TYPES, entity
from db import conn

TEXT_REF = re.compile("<@(\d+)>")
SELF = object()
UNSET = object()
class lazy:
    def __init__(self, name):
        self.value = UNSET
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if getattr(instance, f"_{self.name}", UNSET) is UNSET:
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
            return f'<input class="rename-input" name="name" value="{self.name}" hx-post="/entity-types/{self.id}/rename" hx-swap="outerHTML">'
        elif fmt == "heading":
            return f'<h2 hx-get="/entity-types/{self.id}/rename" hx-swap="outerHTML">{self.name}</h2>'
        else:
            return f"""<a
                class="clickable entity-type"
                hx-push-url="true"
                hx-get="/entity-types/{self.id}"
                hx-select="#container"
                hx-target="#container"
            ><strong>{self.name}</strong></a>"""

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
            return f'<input class="rename-input" name="name" value="{self.name}" hx-post="/entities/{self.id}/rename" hx-swap="outerHTML">'
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
            """
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
            """
            SELECT
                id
            FROM facts
            WHERE subject_id = ?
            """,
            (self.id,),
        ).fetchall():
            yield Fact(row["id"])

    @property
    def incoming_facts(self):
        cur = conn.cursor()
        for row in cur.execute(
            """
            SELECT
                f.id
            FROM facts f
            LEFT JOIN properties p
            ON f.property_id = p.id
            WHERE f.object_id = ? AND (p.reflected_property_id IS NULL OR p.reflected_property_id <> p.id)
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
            """
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
            return f"""<span class="property">
                    {self.subject_type}
                <a
                    class="clickable"
                    hx-push-url="true"
                    hx-get="/properties/{self.id}"
                    hx-select="#container"
                    hx-target="#container"
                >{self.label}</a> {self.object_type or self.data_type}{arrow}</span>"""
        elif fmt == "rename-form":
            return f'<input class="rename-input" name="name" value="{self.label}" hx-post="/properties/{self.id}/rename" hx-swap="outerHTML">'
        elif fmt == "heading":
            return f'<h2 hx-get="/properties/{self.id}/rename" hx-swap="outerHTML">{self.label}</h2>'
        else:
            return f"""<a
                class="clickable property"
                hx-get="/properties/{self.id}"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
            >{self.label}</a>"""

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE properties
            SET label=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        conn.commit()
        self.label = name

    def __str__(self):
        return f"{self}"


class Fact(Model):
    fields = ("subj", "prop", "obj", "reflected_fact", "created_at", "updated_at", "valid_from", "valid_until")
    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                subject_id,
                property_id,
                value,
                object_id,
                reflected_fact_id,
                created_at,
                updated_at,
                valid_from,
                valid_until
            FROM
                facts
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Fact with this ID found")
        self.subj = Entity(row["subject_id"])
        self.prop = Property(row["property_id"])
        if row["object_id"]:
            self.obj = Entity(row["object_id"])
        else:
            self.obj = Plain.decode(self.prop.data_type, row["value"])
        if row["reflected_fact_id"]:
            self.reflected_fact = +Fact(row["reflected_fact_id"])
        else:
            self.reflected_fact = None
        self.created_at = row["created_at"]
        self.updated_at = row["updated_at"]
        self.valid_from = datetime.strptime(row["valid_from"], "%Y-%m-%d") if row["valid_from"] else None
        self.valid_until = datetime.strptime(row["valid_until"], "%Y-%m-%d") if row["valid_until"] else None

    @property
    def is_valid(self):
        now = datetime.utcnow()
        return (
            (not self.valid_from or now >= self.valid_from)
            and
            (not self.valid_until or now <= self.valid_until)
        )


    @classmethod
    def all_of_same_date(cls):
        cur = conn.cursor()
        return [
            cls(row[0])
            for row in cur.execute(
                """
                SELECT f.id
                FROM facts f
                LEFT JOIN properties p ON f.property_id = p.id
                WHERE p.data_type = 'date' AND f.value LIKE '%-' || ?
                """,
                (date.today().strftime("%m-%d"),),
            )
        ]

    def delete(self):
        cur = conn.cursor()
        if self.reflected_fact:
            cur.execute("DELETE FROM facts WHERE id = ?", (self.reflected_fact.id,))
            # evict deleted fact from cache:
            self._cache.pop(self.reflected_fact.id)
        cur.execute("DELETE FROM facts WHERE id = ?", (self.id,))
        # evict deleted fact from cache:
        self._cache.pop(self.id)

    def set_value(self, value):
        cur = conn.cursor()
        if self.prop.data_type.name == "entity":
            cur.execute(
                """
                    UPDATE facts
                    SET object_id = ?, updated_at = datetime('now')
                    WHERE id = ?
                """,
                (
                    value.id, self.id
                ),
            )
            if self.reflected_fact:
                cur.execute("DELETE FROM facts WHERE id = ?", (self.reflected_fact.id,))
                # evict deleted fact from cache:
                self._cache.pop(self.reflected_fact.id)
            self._create_reflected_fact(
                cur,
                fact_id=self.id,
                subj=self.subj,
                obj=value,
                prop=self.prop,
            )
        else:
            cur.execute("""
                UPDATE facts
                SET value = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    value.encode(), self.id,
                ),
            )
        conn.commit()
        self.populate()

    def set_validity(self, valid_from=UNSET, valid_until=UNSET):
        cur = conn.cursor()
        if valid_from is not UNSET:
            self.valid_from = datetime.strptime(valid_from, "%Y-%m-%d")
        if valid_until is not UNSET:
            self.valid_until = datetime.strptime(valid_until, "%Y-%m-%d")
        cur.execute("""
            UPDATE facts
            SET valid_from = ?, valid_until = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                f"{self.valid_from:%Y-%m-%d}" if self.valid_from else None,
                f"{self.valid_until:%Y-%m-%d}" if self.valid_until else None,
                self.id,
            ),
        )
        conn.commit()

    @classmethod
    def new(cls, entity, prop, value):
        cur = conn.cursor()
        if prop.data_type.name == "entity":
            cur.execute(
                """
                    INSERT INTO facts
                        (subject_id, property_id, object_id)
                    VALUES
                        (?, ?, ?)
                """,
                (
                    entity.id, prop.id, value.id
                ),
            )
            first_fact_id = cur.lastrowid
            cls._create_reflected_fact(
                cur,
                fact_id=first_fact_id,
                subj=entity,
                obj=value,
                prop=prop,
            )
        else:
            cur.execute("""
                INSERT INTO facts
                    (subject_id, property_id, value)
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

    @staticmethod
    def _create_reflected_fact(cur, *, fact_id, subj, obj, prop):
        if prop.reflected_property:
            cur.execute(
                """
                    INSERT INTO facts
                        (subject_id, property_id, object_id, reflected_fact_id)
                    VALUES
                        (?, ?, ?, ?)
                """,
                (
                    obj.id, prop.reflected_property.id, subj.id, fact_id
                ),
            )
            cur.execute(
                """
                    UPDATE facts
                    SET reflected_fact_id = ?
                    WHERE id = ?
                """,
                (cur.lastrowid, fact_id),
            )

    def __format__(self, fmt):
        if self.is_valid:
            maybe_invalid = ""
            validity_msg = ""
        else:
            maybe_invalid = " invalid" if not self.is_valid else ""

            validity_msg = f"""<span class="validity">valid
                {f"from {self.valid_from:%Y-%m-%d}" if self.valid_from else ""}
                {f"until {self.valid_until:%Y-%m-%d}" if self.valid_until else ""}
                </span>
            """
        if fmt == "heading":
            edit_button = f'<a hx-target="closest h2" hx-get="/facts/{self.id}/edit">✎</a>'
            delete_button = f'<a hx-confirm="Are you sure you want to delete this fact?" hx-delete="/facts/{self.id}">⌫</a>'
            return f"<h2>{self} {edit_button}{delete_button}</h2>"
        elif fmt == "short":
            info_button = f"""<a
                class="hovershow clickable"
                hx-get="/facts/{self.id}"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
            >ⓘ</a>"""
            edit_button = f'<a hx-target="closest .obj" class="hovershow" hx-get="/facts/{self.id}/edit">✎</a>'
            delete_button = f'<a hx-target="closest .vp" class="hovershow" hx-confirm="Are you sure you want to delete this fact?" hx-delete="/facts/{self.id}">⌫</a>'
            return f"""<span class="vp{maybe_invalid}">
                {self.prop}
                <span class="obj">{self.obj}{validity_msg}{info_button}{edit_button}{delete_button}</span>
            </span>
            <span class="hovershow" style="font-size: xx-small;">created {self.created_at} {f", updated {self.updated_at}" if self.updated_at else ""}</span>
            """
        elif fmt == "valid_from":
            return f'<span class="clickable validity-editable" hx-get="/facts/{self.id}/change-valid-from" hx-swap="outerHTML">{self.valid_from or "(null)"}</span>'
        elif fmt == "valid_until":
            return f'<span class="clickable validity-editable" hx-get="/facts/{self.id}/change-valid-until" hx-swap="outerHTML">{self.valid_until or "(null)"}</span>'
        else:
            return f"""<span class="fact{maybe_invalid}">
                {self.subj}
                <span class="vp">
                    {self.prop}
                    {self.obj}
                </span>
                {validity_msg}
            </span>
            <span class="hovershow" style="font-size: xx-small;">created {self.created_at} {f", updated {self.updated_at}" if self.updated_at else ""}</span>
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
        text = self.data_type.display_html(self.value)
        for ref_id, entity in {
            ref_id: Entity(ref_id) for ref_id in set(map(int, TEXT_REF.findall(text)))
        }.items():
            text = text.replace(f"<@{ref_id}>", str(entity))
        return text
