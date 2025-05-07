import re
from datetime import date

from data_types import TYPES
from db import (
    conn,
    make_search_key,
    LABEL,
    IS_A,
    AVATAR,
    ROOT,
    VALID_FROM,
    VALID_UNTIL,
    DATA_LABELS,
)

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


class Verb(Model):
    fields = (
        "label",
        "data_type",
        "internal",
    )
    table_name = "verbs"

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                label,
                data_type,
                internal
            FROM verbs
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Verb with this ID found")
        self.label = row["label"]
        self.data_type = TYPES[row["data_type"]]
        self.internal = row["internal"]

    @classmethod
    def new(
        cls,
        label,
        *,
        data_type,
    ):
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO
                verbs
                (
                    label,
                    data_type,
                    internal
                ) VALUES (?, ?, FALSE)
            """,
            (
                label,
                data_type.name,
            ),
        )
        verb_id = cur.lastrowid
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('verbs', ?, ?)",
            (cur.lastrowid, make_search_key(label)),
        )
        conn.commit()
        return Verb(verb_id)

    def claims(self, page_no=0, page_size=20):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM claims
            WHERE verb_id = ?
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (self.id,),
        ).fetchall():
            yield Claim(row["id"])

    @classmethod
    def all(
        cls,
        *,
        data_type=None,
        order_by="id ASC",
        page_no=0,
        page_size=20,
    ):
        conditions = ["1=1"]
        values = []
        if data_type is not None:
            conditions.append("data_type LIKE ?")
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
            return f"""<span class="verb">
                <a class="clickable" href="/verbs/{self.id}">{self.label}</a>
                {self.data_type}</span>"""
        elif fmt == "heading":
            return f"""<h2>{self.label}</h2>"""
        else:
            return f"""<a
                class="clickable verb"
                href="/verbs/{self.id}"
            >{self.label}</a>"""

    def rename(self, name):
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE verbs
            SET label=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        conn.commit()
        self.label = name

    def __str__(self):
        return f"{self}"


class Claim(Model):
    fields = (
        "subject",
        "verb",
        "object",
    )
    table_name = "claims"

    def populate(self):
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT
                subject_id,
                verb_id,
                value,
                object_id
            FROM
                claims
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No Claim with this ID found")
        if row["subject_id"]:
            self.subject = Claim(row["subject_id"])
        else:
            self.subject = None
        self.verb = Verb(row["verb_id"])
        if row["object_id"]:
            self.object = Claim(row["object_id"])
        elif row["value"] is not None:
            self.object = Plain.decode(self.verb, row["value"])
        else:
            # ROOT claim
            self.object = None

    @classmethod
    def all(cls, *, subject_id=None, verb_ids=None, object_id=None, order_by="id ASC", page_no=0, page_size=20):
        cur = conn.cursor()
        conditions = ["1=1"]
        bindings = []
        if subject_id is not None:
            conditions.append("subject_id = ?")
            bindings.append(subject_id)
        if object_id is not None:
            conditions.append("object_id = ?")
            bindings.append(object_id)
        if verb_ids is not None:
            conditions.append(
                f"verb_id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
            )
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM claims c
            WHERE {" AND ".join(conditions)}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            tuple(bindings)
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def all_of_same_month(cls, reference_date=None):
        cur = conn.cursor()
        if reference_date is None:
            reference_date = date.today()
        return [
            cls(row[0])
            for row in cur.execute(
                """
                SELECT c.id
                FROM claims c
                LEFT JOIN verbs v ON c.verb_id = v.id
                WHERE v.id != ? AND v.id != ? AND v.data_type = 'date' AND c.value LIKE '%-' || ? || '-%'
                """,
                (VALID_FROM, VALID_UNTIL, reference_date.strftime("%m"),),
            )
        ]

    @classmethod
    def search(cls, q, *, page_size=20, page_no=0, category_id=None):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM search_index
            WHERE table_name = 'claims'
            AND value LIKE '%' || ? || '%'
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (make_search_key(q),),
        ).fetchall():
            yield cls(row["id"])

    def incoming_claims(self):
        cur = conn.cursor()
        for row in cur.execute(
            """
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE c.object_id = ?
            AND v.data_type <> 'undirected_link'
            """,
            (self.id,),
        ).fetchall():
            yield Claim(row["id"])

    def incoming_mentions(self):
        cur = conn.cursor()
        for row in cur.execute(
            """
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE c.value LIKE '%<@' || ? || '>%'
            """,
            (self.id,),
        ).fetchall():
            yield Claim(row["id"])

    def outgoing_claims(self):
        cur = conn.cursor()
        for row in cur.execute(
            """
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE c.subject_id = ?
            OR (v.data_type = 'undirected_link' AND c.object_id = ?)
            """,
            (self.id, self.id),
        ).fetchall():
            yield Claim(row["id"])

    @classmethod
    def all_labelled(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                c.id AS id
            FROM claims c
            LEFT JOIN claims l
            ON l.subject_id = c.id
            WHERE l.verb_id = {LABEL}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def all_categories(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                DISTINCT(object_id) AS id
            FROM claims c
            WHERE c.verb_id = {IS_A}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        ).fetchall():
            yield cls(row["id"])

    def delete(self):
        cur = conn.cursor()
        cur.execute("DELETE FROM claims WHERE id = ?", (self.id,))
        # evict deleted claim from cache:
        conn.commit()
        self._cache.pop(self.id)

    def set_value(self, value):
        cur = conn.cursor()
        if self.verb.data_type.name.endswith("directed_link"):
            raise RuntimeError("Can't edit link; delete it and create it again")
        else:
            cur.execute("""
                UPDATE claims
                SET value = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    value.encode(), self.id,
                ),
            )
            if self.verb.id == LABEL:
                cur.execute(
                    "UPDATE search_index SET value=? WHERE table_name=? AND id=?",
                    (make_search_key(value.encode()), 'claims', self.subject.id),
                )
        conn.commit()
        self.populate()

    @classmethod
    def new(cls, subject, verb, value_or_object):
        cur = conn.cursor()
        if verb.data_type.name.endswith("directed_link"):
            # "entity"
            cur.execute(
                """
                    INSERT INTO claims
                        (subject_id, verb_id, object_id)
                    VALUES
                        (?, ?, ?)
                """,
                (
                    subject.id, verb.id, value_or_object.id
                ),
            )
        else:
            cur.execute("""
                INSERT INTO claims
                    (subject_id, verb_id, value)
                VALUES
                    (?, ?, ?)
                """,
                (
                    subject.id, verb.id, value_or_object.encode()
                ),
            )
        conn.commit()
        return Claim(cur.lastrowid)

    @classmethod
    def new_root(cls, name):
        cur = conn.cursor()
        cur.execute("INSERT INTO claims (verb_id) VALUES (?)", (ROOT,))
        new_id = cur.lastrowid
        cur.execute(
            "INSERT INTO claims (subject_id, verb_id, value) VALUES (?, ?, ?)",
            (new_id, LABEL, name),
        )
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('claims', ?, ?)",
            (new_id, make_search_key(name)),
        )
        conn.commit()
        return Claim(new_id)

    def get_data(self):
        data = {}
        for cl in Claim.all(subject_id=self.id, verb_ids=DATA_LABELS):
            data.setdefault(cl.verb.id, []).append(cl)
        return data

    def _get_remarks(self, data):
        today = date.today()
        remarks = []
        css_classes = set()
        if (
            VALID_FROM in data
            and date.fromisoformat(data[VALID_FROM][0].object.value) > today
        ):
            css_classes.add("invalid")
            remarks.append(f"from {data[VALID_FROM][0].object.value}")
        elif (
            VALID_UNTIL in data
            and date.fromisoformat(data[VALID_UNTIL][0].object.value) < today
        ):
            css_classes.add("invalid")
            remarks.append(f"until {data[VALID_UNTIL][0].object.value}")

        if remarks:
            remarks = f''' data-tooltip="{', '.join(remarks)}"'''
        else:
            remarks = ""
        return f" {' '.join(css_classes)}" if css_classes else "", remarks

    def __format__(self, fmt):
        data = self.get_data()
        css_classes, remarks = self._get_remarks(data)
        if fmt == "label":
            if LABEL in data:
                return data[LABEL][0].object.value
            else:
                return f"Claim #{self.id}"
        elif fmt == "link" or not fmt:
            if LABEL in data:
                return f'<a{remarks} class="claim-link{css_classes}" href="/claims/{self.id}">{self:avatar}{data[LABEL][0].object.value}</a>'
            else:
                return f'{self:svo}'
        elif fmt == "heading":
            if IS_A in data:
                cat = f"""<br><small>&lt;{", ".join(f'<span>{c:handle}{c.object:link}</span>' for c in data[IS_A])}&gt;</small>"""
            else:
                cat = ""
            buttons = []
            if isinstance(self.object, Plain):
                buttons.append(f"""<a
                    hx-target="#edit-area"
                    hx-get="/claims/{self.id}/edit"
                    role="button"
                    class="outline contrast toolbutton"
                >✎ Edit</a>""")
            if not list(self.outgoing_claims()) and not list(self.incoming_claims()):
                buttons.append(f"""<a
                    hx-target="#edit-area"
                    hx-delete="/claims/{self.id}"
                    hx-confirm="Are you sure you want to delete this claim?"
                    role="button"
                    class="outline contrast toolbutton"
                >\N{WASTEBASKET}\ufe0e Delete</a>""")
            if LABEL in data:
                if self.verb.id == ROOT:
                    label = data[LABEL][0]
                    return f"""<h2>{label:handle}{label.object.value} {cat}</h2>{" ".join(buttons)}"""
                else:
                    # non-roots should still show their actual SVO
                    return f"""<h2>{label:handle}{label.object.value} {cat}<br>{self:svo}</h2>{" ".join(buttons)}"""
            else:
                return f"""<h2>{self:svo}</h2>{" ".join(buttons)}"""
        elif fmt.startswith("vo:"):
            subj_id = int(fmt[3:])
            # Handle undirected links properly (always display the _other_ claim)
            if self.subject.id == subj_id:
                return f'<span{remarks} class="vo{css_classes}">{self:handle}{self.verb:link} {self.object:link}</span>'
            else:
                return f'<span{remarks} class="vo{css_classes}">{self:handle}{self.verb:link} {self.subject:link}</span>'
        elif fmt == "sv":
            return f'<span{remarks} class="sv{css_classes}">{self:handle}{self.subject:link} {self.verb:link}</span>'
        elif fmt == "svo":
            return f'<span{remarks} class="svo{css_classes}">{self:handle}{self.subject:link} {self.verb:link} {self.object:link}</span>'
        elif fmt == "handle":
            return f'<a class="handle" href="/claims/{self.id}">↱</a>'
        elif fmt == "ac-result":
            return f"""<span
                class="clickable ac-result"
                hx-target="closest .ac-widget"
                hx-swap="innerHTML"
                hx-get="/claims/autocomplete/accept/{self.id}"
            >{self:label}</span>"""
        elif fmt == "avatar":
            if AVATAR not in data:
                return ""
            return f'<img src="{data[AVATAR][0].object.value}" class="avatar">'
        return f"TODO: {fmt!r}"

    def __str__(self):
        return f"{self:link}"

    def graph_elements(self, verbs=None):
        node = {
            "group": "nodes",
            "data": {
                "label": f"{self:label}",
                "id": str(self.id),
            },
        }
        edges = []
        for link in self.outgoing_claims():
            if not link.verb.data_type.name.endswith("directed_link"):
                continue
            if verbs and link.verb not in verbs:
                continue
            if self.id == link.object.id:
                continue
            if link.verb.id in (IS_A, ROOT):
                continue
            edges.append({
                "group": "edges",
                "data": {
                    "source": str(self.id),
                    "target": str(link.object.id),
                    "label": link.verb.label,
                },
            })
        return node, edges


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
        q_id = cur.lastrowid
        cur.execute(
            "INSERT INTO search_index (table_name, id, value) VALUES ('queries', ?, ?)",
            (q_id, make_search_key(label)),
        )
        conn.commit()
        return cls(q_id)

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
            """
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

    @classmethod
    def from_form(cls, prop, form):
        return Plain(prop.data_type.extract_value(form), prop)

    @classmethod
    def decode(cls, prop, value):
        return Plain(prop.data_type.decode(value), prop)

    def encode(self):
        return self.prop.data_type.encode(self.value)

    def __format__(self, fmt):
        return str(self)

    def __str__(self):
        text = self.prop.data_type.display_html(self.value)
        for ref_id, claim in {
            ref_id: Claim(ref_id) for ref_id in set(map(int, TEXT_REF.findall(text)))
        }.items():
            text = text.replace(f"<@{ref_id}>", f"{claim:link}")
        return text
