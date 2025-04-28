import re
from datetime import date, datetime

from property_types import TYPES
from db import conn, make_search_key

TEXT_REF = re.compile(r"<@(\d+)>")
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
    def all(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        ).fetchall():
            yield cls(row["id"])


class Category(Model):
    table_name = "categories"
    fields = ("name",)

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
                SELECT
                    id, name
                FROM categories
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Category with this ID found")
        self.name = row["name"]

    @classmethod
    def new(cls, name):
        cur = conn.cursor()
        cur.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return cls(cur.lastrowid)

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE categories
            SET name=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        conn.commit()
        self.name = name

    def __format__(self, fmt):
        if fmt == "heading":
            return f"""<h2
                hx-post="/categories/{self.id}/rename"
                hx-swap="outerHTML"
                hx-trigger="blur delay:500ms"
                hx-target="closest h2"
                hx-vals="javascript: name:htmx.find('h2').innerHTML"
                contenteditable
            >{self.name}</h2>"""
        else:
            return f"""<a
                class="clickable category"
                hx-push-url="true"
                href="/categories/{self.id}"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
            ><strong>{self.name}</strong></a>"""

    def __str__(self):
        return f"{self}"


class Entity(Model):
    fields = ("name", "category", "has_avatar")
    table_name = "entities"

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
                SELECT name, category_id, has_avatar
                FROM entities
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Entity with this ID found")
        self.name = row["name"]
        self.category = Category(row["category_id"])
        self.has_avatar = bool(row["has_avatar"])

    @classmethod
    def new(cls, name, category):
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO entities (name, search_key, category_id) VALUES (?, ?, ?)",
            (name, make_search_key(name), category.id),
        )
        conn.commit()
        return Entity(cur.lastrowid)

    @classmethod
    def search(cls, q, *, page_size=20, page_no=0, category_id=None):
        cur = conn.cursor()
        conditions = [
            "search_key LIKE '%' || ? || '%'"
        ]
        bindings = [make_search_key(q)]
        if category_id is not None:
            conditions.append("category_id = ?")
            bindings.append(category_id)
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM entities
            WHERE {" AND ".join(conditions)}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            tuple(bindings),
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def all(cls, *, order_by="id ASC", categories=None, page_no=0, page_size=20):
        conditions = ["1=1"]
        values = []
        if categories is not None:
            # I can't get the parametrized form to work, "category_id IN ?"
            # doesn't want to work with either of tuple/list/set, despite
            # "category_id = ?" working previously. Given that we know these
            # are ints here this is safe to do, but I still don't like it.
            conditions.append(
                f"category_id IN ({','.join(str(c.id) for c in categories)})"
            )
            # values.append(tuple(category.id for category in categories))

        cur = conn.cursor()
        query = f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            WHERE {" AND ".join(conditions)}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
        """
        for row in cur.execute(
            query,
            tuple(values),
        ).fetchall():
            yield cls(row["id"])

    def avatar_form(self):
        return f"""<form
            id="uploadform"
            class="avatar-form"
            hx-put="/entities/{self.id}/avatar"
            hx-encoding="multipart/form-data"
            hx-trigger="change from:input.avatar-upload"
            hx-target="closest header"
            hx-swap="innerHTML"
        >
            <label for="avatar-upload">⇪</label>
            <input id="avatar-upload" class="avatar-upload" type="file" name="file">
        </form>"""

    def __format__(self, fmt):
        if fmt == "heading":
            return f"""
            {f'<img src="/entities/{self.id}/avatar" class="avatar">' if self.has_avatar else ''}
            <h2>
            {self.avatar_form() if not self.has_avatar else ''}
            <span
                hx-post="/entities/{self.id}/rename"
                hx-swap="outerHTML"
                hx-trigger="blur delay:500ms"
                hx-target="closest h2"
                hx-vals="javascript: name:htmx.find('span').innerHTML"
                contenteditable
            >{self.name}</span> <small>{self.category}</small></h2>"""
        elif fmt == "full":
            return f"""<a
                class="clickable entity-link"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
                href="/entities/{self.id}"
            >
            {f'<img src="/entities/{self.id}/avatar" class="avatar">' if self.has_avatar else ''}
            {self.name}</a> <small>{self.category}</small>"""
        elif fmt.startswith("ac-result"):
            category_id = fmt.split(":")[-1]
            return f"""<span
                class="clickable ac-result"
                hx-target="closest .ac-widget"
                hx-swap="innerHTML"
                hx-get="/entities/autocomplete/accept/{category_id}/{self.id}"
            >{self.name}</span>"""
        else:
            return f"""<a
                class="clickable entity-link"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
                href="/entities/{self.id}">
                {f'<img src="/entities/{self.id}/avatar" class="avatar">' if self.has_avatar else ''}
                {self.name}</a>"""

    def __str__(self):
        return f"{self}"

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE entities
            SET name=?, search_key=?
            WHERE id = ?
            """,
            (name, make_search_key(name), self.id),
        )
        conn.commit()
        self.name = name

    def upload_avatar(self, file):
        with open(f"avatars/{self.id}.jpg", "wb") as f:
            f.write(file)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE entities
            SET has_avatar=?
            WHERE id = ?
            """,
            (1, self.id),
        )
        conn.commit()
        self.has_avatar = True

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

    def graph_elements(self, target_categories=None, properties=None):
        yield {
            "group": "nodes",
            "data": {
                "label": self.name,
                "id": str(self.id),
            },
        }
        for fact in self.facts:
            if not isinstance(fact.obj, Entity):
                continue
            if properties and fact.prop not in properties:
                continue
            if fact.reflected_fact and fact.reflected_fact.id < fact.id:
                continue
            if target_categories and fact.obj.category not in target_categories:
                continue
            yield {
                "group": "edges",
                "data": {
                    "source": str(self.id),
                    "target": str(fact.obj.id),
                    "label": fact.prop.label,
                },
            }


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
            WHERE (
                f.object_id = ?
                AND p.reflected_property_id IS NULL
            ) OR f.value LIKE '%<@' || ? || '>%'
            """,
            (self.id, self.id),
        ).fetchall():
            yield Fact(row["id"])


class Property(Model):
    fields = (
        "label",
        "data_type",
        "extra_data",
        "subject_category",
        "object_category",
        "reflected_property",
    )
    table_name = "properties"

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                label,
                data_type,
                extra_data,
                subject_category_id,
                object_category_id,
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
        self.subject_category = Category(row["subject_category_id"])
        if row["object_category_id"]:
            # relation to an entity
            self.object_category = Category(row["object_category_id"])
        else:
            self.object_category = None
        if row["reflected_property_id"]:
            self.reflected_property = Property(row["reflected_property_id"])
        else:
            self.reflected_property = None

    @classmethod
    def new(
        cls,
        label,
        *,
        data_type,
        subject_category,
        reflected_property_name=None,
        object_category=None,
        extra_data=None,
    ):
        if reflected_property_name and data_type.name != "entity":
            raise ValueError(
                f"Reflexivity only makes sense with entities, not with {data_type}.",
            )
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO
                properties
                (
                    label,
                    data_type,
                    extra_data,
                    subject_category_id,
                    object_category_id
                ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                label,
                data_type.name,
                extra_data,
                subject_category.id,
                object_category and object_category.id,
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
                    """
                    INSERT INTO properties (
                        label,
                        data_type,
                        reflected_property_id,
                        subject_category_id,
                        object_category_id
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        reflected_property_name,
                        data_type.name,
                        first_property_id,
                        object_category.id,
                        subject_category.id,
                    ),
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
    def all(
        cls,
        *,
        subject_category=None,
        object_category=None,
        data_type=None,
        order_by="id ASC",
        page_no=0,
        page_size=20,
    ):
        conditions = ["1=1"]
        values = []
        if subject_category is not None:
            conditions.append("subject_category_id = ?")
            values.append(subject_category.id)
        if object_category is not None:
            conditions.append("object_category_id = ?")
            values.append(object_category.id)
        if data_type is not None:
            conditions.append("data_type = ?")
            values.append(data_type)

        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM {getattr(cls, "table_name", f"{cls.__name__.lower()}s")}
            WHERE {" AND ".join(conditions)}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            tuple(values),
        ).fetchall():
            yield cls(row["id"])

    def __format__(self, fmt):
        if fmt == "full":
            arrow = (
                "" if self.object_category is None  # not a entity-entity link
                else "⭢" if self.reflected_property is None
                else "⮂" if self.reflected_property.id != self.id
                else "⭤"
            )
            return f"""<span class="property">
                    {self.subject_category}
                <a
                    class="clickable"
                    hx-push-url="true"
                    href="/properties/{self.id}"
                    hx-select="#container"
                    hx-target="#container"
                    hx-swap="outerHTML"
                >{self.label}</a> {self.object_category or self.data_type}{arrow}</span>"""
        elif fmt == "heading":
            return f"""<h2
                hx-post="/properties/{self.id}/rename"
                hx-swap="outerHTML"
                hx-trigger="blur delay:500ms"
                hx-target="closest h2"
                hx-vals="javascript: name:htmx.find('h2').innerHTML"
                contenteditable
            >{self.label}</h2>"""
        else:
            return f"""<a
                class="clickable property"
                href="/properties/{self.id}"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
            >{self.label}</a>"""

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            """
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
    fields = (
        "subj",
        "prop",
        "obj",
        "reflected_fact",
        "created_at",
        "updated_at",
        "valid_from",
        "valid_until",
    )

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
            self.obj = Plain.decode(self.prop, row["value"])
            self.obj.fact = self
        if row["reflected_fact_id"]:
            self.reflected_fact = +Fact(row["reflected_fact_id"])
        else:
            self.reflected_fact = None
        self.created_at = row["created_at"]
        self.updated_at = row["updated_at"]
        self.valid_from = (
            datetime.strptime(row["valid_from"], "%Y-%m-%d")
            if row["valid_from"]
            else None
        )
        self.valid_until = (
            datetime.strptime(row["valid_until"], "%Y-%m-%d")
            if row["valid_until"]
            else None
        )

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

    @classmethod
    def all_of_same_month(cls, reference_date=None):
        cur = conn.cursor()
        if reference_date is None:
            reference_date = date.today()
        return [
            cls(row[0])
            for row in cur.execute(
                """
                SELECT f.id
                FROM facts f
                LEFT JOIN properties p ON f.property_id = p.id
                WHERE p.data_type = 'date' AND f.value LIKE '%-' || ? || '-%'
                """,
                (reference_date.strftime("%m"),),
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
        if self.reflected_fact:
            if valid_from is not UNSET:
                self.reflected_fact.valid_from = datetime.strptime(
                    valid_from,
                    "%Y-%m-%d",
                )
            if valid_until is not UNSET:
                self.reflected_fact.valid_until = datetime.strptime(
                    valid_until,
                    "%Y-%m-%d",
                )
            cur.execute("""
                UPDATE facts
                SET valid_from = ?, valid_until = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    (
                        f"{self.reflected_fact.valid_from:%Y-%m-%d}"
                        if self.reflected_fact.valid_from
                        else None
                    ),
                    (
                        f"{self.reflected_fact.valid_until:%Y-%m-%d}"
                        if self.reflected_fact.valid_until
                        else None
                    ),
                    self.reflected_fact.id,
                ),
            )
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
            edit_button = f"""<a
                hx-target="closest h2"
                hx-get="/facts/{self.id}/edit"
            >✎</a>"""
            delete_button = f"""<a
                hx-confirm="Are you sure you want to delete this fact?"
                hx-delete="/facts/{self.id}"
            >⌫</a>"""
            return f"<h2>{self} {edit_button}{delete_button}</h2>"
        elif fmt == "short":
            info_button = f"""<a
                class="hovershow clickable"
                href="/facts/{self.id}"
                hx-push-url="true"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
            >ⓘ</a>"""
            edit_button = f"""<a
                hx-target="closest .obj" class="hovershow"
                hx-get="/facts/{self.id}/edit"
            >✎</a>"""
            delete_button = f"""<a
                hx-target="closest .vp" class="hovershow"
                hx-confirm="Are you sure you want to delete this fact?"
                hx-delete="/facts/{self.id}"
            >⌫</a>"""
            return f"""<span class="vp{maybe_invalid}">
                {self.prop}
                <span class="obj">
                    {self.obj}{validity_msg}
                    {info_button}
                    {edit_button}
                    {delete_button}
                </span>
            </span>
            """
        elif fmt == "valid_from":
            return f"""<span
                class="clickable validity-editable"
                hx-get="/facts/{self.id}/change-valid-from"
                hx-swap="outerHTML"
            >{self.valid_from or "(null)"}</span>"""
        elif fmt == "valid_until":
            return f"""<span
                class="clickable validity-editable"
                hx-get="/facts/{self.id}/change-valid-until"
                hx-swap="outerHTML"
            >{self.valid_until or "(null)"}</span>"""
        else:
            return f"""<span class="fact{maybe_invalid}">
                {self.subj}
                <span class="vp">
                    {self.prop}
                    {self.obj}
                </span>
                {validity_msg}
            </span>
            """

    def __str__(self):
        return f"{self}"


class Query(Model):
    table_name = "queries"
    fields = ("label", "sql",)

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
                SELECT
                    id, label, sql
                FROM queries
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Query with this ID found")
        self.label = row["label"]
        self.sql = row["sql"]

    @classmethod
    def new(cls, label, sql):
        cur = conn.cursor()
        cur.execute("INSERT INTO queries (label, sql) VALUES (?, ?)", (label, sql))
        conn.commit()
        return cls(cur.lastrowid)

    def rename(self, label):
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE queries
            SET label=?
            WHERE id = ?
            """,
            (label, self.id),
        )
        conn.commit()
        self.label = label

    def __format__(self, fmt):
        if fmt == "heading":
            return f"""<h2
            >{self.label} <a
                href="/queries/{self.id}/edit"
            >✎</a></h2>"""
        else:
            return f"""<a
                class="clickable query"
                hx-push-url="true"
                href="/queries/{self.id}"
                hx-select="#container"
                hx-target="#container"
                hx-swap="outerHTML"
            ><strong>{self.label}</strong></a>"""

    def run(self, page_no, page_size):
        cur = conn.cursor()
        cur.execute(
            f"""
            {self.sql}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        )
        return cur.fetchall()

    def update(self, sql, label):
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE queries
            SET label=?, sql=?
            WHERE id=?
            """,
            (label, sql, self.id),
        )
        conn.commit()
        self.sql = sql
        self.label = label

    def __str__(self):
        return f"{self}"


class Plain:
    def __init__(self, value, prop):
        self.value = value
        self.prop = prop
        self.fact = None

    @classmethod
    def from_form(cls, prop, form):
        return Plain(prop.data_type.extract_value(form), prop)

    @classmethod
    def decode(cls, prop, value):
        return Plain(prop.data_type.decode(value), prop)

    def encode(self):
        return self.prop.data_type.encode(self.value)

    def __str__(self):
        text = self.prop.data_type.display_html(
            self.value,
            prop=self.prop,
            fact=self.fact,
        )
        for ref_id, entity in {
            ref_id: Entity(ref_id) for ref_id in set(map(int, TEXT_REF.findall(text)))
        }.items():
            text = text.replace(f"<@{ref_id}>", str(entity))
        return text
