import graphlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from functools import cache, cached_property
from html import escape
from itertools import combinations, count
from urllib.parse import quote_plus

from veronique import db
from veronique.constants import CLAIM_DATA_CACHE_TIME, SESSION_MAX_AGE
from veronique.context import context
from veronique.data_types import TYPES
from veronique.db import (
    AVATAR,
    COMMENT,
    DATA_LABELS,
    IS_A,
    LATLON,
    ROOT,
    SOURCE,
    VALID_FROM,
    VALID_UNTIL,
)
from veronique.html import H, join
from veronique.nomnidate import NonOmniscientDate
from veronique.search import find, update_index_for_doc
from veronique.security import hash_password, sign
from veronique.settings import settings as S
from veronique.utils import timed_cache

SELF = object()
UNSET = object()

HANDLE = "\N{UPWARDS ARROW WITH TIP RIGHTWARDS}"


class lazy:
    def __init__(self, name):
        self.value = UNSET
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if getattr(instance, f"_{self.name}", UNSET) is UNSET:
            +instance  # noqa
        return getattr(instance, f"_{self.name}")

    def __set__(self, instance, value):
        setattr(instance, f"_{self.name}", value)


class Model:
    def __new__(cls, id):
        if not isinstance(id, int):
            raise TypeError("IDs need to be ints")
        if id in cls._cache:
            return cls._cache[id]
        obj = super().__new__(cls)
        cls._cache[id] = obj
        obj._populated = False
        return obj

    def __init__(self, id):
        self.id = id

    def url(self, action=None):
        if action:
            return f"/{type(self).table_name}/{self.id}/{action}"
        return f"/{type(self).table_name}/{self.id}"

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
        cur = db.conn.cursor()
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
        "description",
        "data_type",
        "internal",
        "extra",
    )
    table_name = "verbs"

    def populate(self):
        cur = db.conn.cursor()
        row = cur.execute(
            """
            SELECT
                label,
                description,
                data_type,
                internal,
                extra
            FROM verbs
            WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError(f"No Verb with this ID found: {self.id}")
        self.label = row["label"]
        self.description = row["description"] or ""
        self.data_type = TYPES[row["data_type"]]
        self.internal = row["internal"]
        self.extra = row["extra"]

    @classmethod
    def new(
        cls,
        label,
        *,
        description="",
        data_type,
        extra=None,
    ):
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO
                verbs
                (
                    label,
                    description,
                    data_type,
                    internal,
                    extra
                ) VALUES (?, ?, ?, FALSE, ?)
            """,
            (
                label,
                description,
                data_type.name,
                extra,
            ),
        )
        verb_id = cur.lastrowid
        update_index_for_doc(cur, "verbs", cur.lastrowid, label)
        db.conn.commit()
        if data_type.name == "inferred":
            cls.get_inferables.cache_clear()
        return Verb(verb_id)

    @classmethod
    @cache
    def get_inferables(cls):
        result = []
        for inferable in cls.all(data_type="inferred"):
            result.append(Inferable(inferable))
        return result

    def claims(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
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
        only_writable=False,
    ):
        conditions = ["1=1"]
        values = []
        if data_type is not None:
            conditions.append("data_type LIKE ?")
            values.append(data_type)
        if (verb_ids := (context.user.writable_verbs if only_writable else context.user.readable_verbs)) is not None:
            conditions.append(
                f"id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
            )

        cur = db.conn.cursor()
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

    def html(self, fmt=None):
        if not context.user.can("read", "verb", self.id):
            return H("(unknown verb)")
        if fmt == "full":
            return H.span(
                H.a(
                    self.name,
                    href=self.url(),
                    cls="clickable",
                ),
                " ",
                str(self.data_type),
                cls="verb",
            )
        elif fmt == "hamburger":
            parts = []
            if context.user.is_admin:
                parts.append(H.li(
                    H.a(
                        H.i("\N{LOWER RIGHT PENCIL}"),
                        " Edit",
                        hx_target="#edit-area",
                        hx_get=self.url("edit"),
                    ),
                ))
                if self.deletable:
                    parts.append(H.li(
                        H.a(
                            H.i("\N{WASTEBASKET}\ufe0e"),
                            " Delete",
                            hx_target="#edit-area",
                            hx_delete=self.url(),
                            hx_confirm="Are you sure you want to delete this verb?",
                        )
                    ))
            if parts:
                return H.details(
                    H.summary("\N{TRIGRAM FOR HEAVEN}"),
                    H.ul(
                        *parts,
                        dir="rtl",
                    ),
                    cls="dropdown hamburger",
                )
            else:
                return None
        elif fmt == "heading":
            return H.h2(self.name)
        elif fmt == "detail":
            return self.data_type.detail_for(self)
        elif fmt == "edit":
            if hasattr(self.data_type, "edit_verb_form"):
                return self.data_type.edit_verb_form(self)
            return None
        elif fmt == "description":
            return H.p(H.em(self.description))
        else:
            return H.a(
                self.name,
                cls="clickable verb",
                href=self.url(),
            )

    def edit(self, form):
        description = form.pop("description", "")
        self.data_type.edit_verb(self, form)
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE verbs
            SET description=?, extra=?
            WHERE id = ?
            """,
            (description, self.extra, self.id),
        )
        db.conn.commit()
        # evict changed verb from cache:
        self._cache.pop(self.id, None)

    def rename(self, name):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE verbs
            SET label=?
            WHERE id = ?
            """,
            (name, self.id),
        )
        db.conn.commit()
        self.label = name
        # evict changed verb from cache:
        self._cache.pop(self.id, None)

    @property
    def deletable(self):
        return not list(self.claims(page_size=1)) and self.id >= 0

    def delete(self):
        if not self.deletable:
            raise ValueError("Can't delete this verb")
        cur = db.conn.cursor()
        cur.execute("DELETE FROM verbs WHERE id = ?", (self.id,))
        cur.execute(
            "DELETE FROM permissions WHERE object = ? AND permission LIKE '%-verb'",
            (self.id,),
        )
        db.conn.commit()
        # evict deleted verb from cache:
        self._cache.pop(self.id, None)
        # This is needed because even though we clear the _verb_ cache cached
        # users can still have permissions for now dead verbs.
        User._cache.clear()

    def can_turn_into(self, other):
        dt_name1 = type(self.data_type).__name__
        dt_name2 = type(other.data_type).__name__
        return dt_name2 in TYPES[dt_name1].compatible_types

    @property
    def name(self):
        if self.id == ROOT:
            return "root (allows creating new entities)"
        return self.label

    def __str__(self):
        return str(self.html())


class Claim(Model):
    fields = (
        "subject",
        "verb",
        "object",
        "owner",
    )
    table_name = "claims"

    @classmethod
    def bulk_populate(cls, ids, deep=False):
        ids = [id for id in ids if id not in cls._cache or not cls._cache[id]._populated]
        if not ids:
            return
        cur = db.conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id,
                subject_id,
                verb_id,
                value,
                object_id,
                created_at,
                updated_at,
                owner_id
            FROM
                claims
            WHERE id IN ({",".join("?"*len(ids))})
            """,
            tuple(ids),
        ).fetchall():
            instance = cls(row["id"])
            instance.populate(row)
            instance._populated = True

        if deep:
            data_claims = {}
            data_ids = []

            for row in cur.execute(
                f"""
                SELECT
                    id, subject_id
                FROM claims c
                WHERE subject_id IN ({",".join("?"*len(ids))})
                """,
                tuple(ids),
            ):
                claim = cls(row["id"])
                data_claims.setdefault(row["subject_id"], []).append(claim)
                data_ids.append(row["id"])
            cls.bulk_populate(data_ids, deep=False)
            for claim_id, data in data_claims.items():
                cls(claim_id).get_data(data)

    def populate(self, row=None):
        cur = db.conn.cursor()
        if row is None:
            row = cur.execute(
                """
                SELECT
                    subject_id,
                    verb_id,
                    value,
                    object_id,
                    created_at,
                    updated_at,
                    owner_id
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
        self.owner = User(row["owner_id"])
        self.created_at = row["created_at"]
        self.updated_at = row["updated_at"]

    @classmethod
    def search(
        cls,
        *,
        q,
        page_size=20,
    ):
        if not (set(q) - {*"1234567890"}):
            claim = cls(int(q))
            if context.user.can("read", "verb", claim.verb.id):
                yield claim

        cur = db.conn.cursor()
        for hit in find(cur, q, table="claims", page_size=page_size):
            claim = cls(hit["id"])
            if context.user.can("read", "verb", claim.verb.id):
                yield claim

    @classmethod
    def all(
        cls,
        *,
        subject_id=None,
        object_id=None,
        verb_id=None,
        order_by="id ASC",
        page_no=0,
        page_size=20,
    ):
        cur = db.conn.cursor()
        conditions = ["1=1"]
        bindings = []
        if subject_id is not None:
            conditions.append("subject_id = ?")
            bindings.append(subject_id)
        if object_id is not None:
            conditions.append("object_id = ?")
            bindings.append(object_id)
        if verb_id is not None:
            conditions.append("verb_id = ?")
            bindings.append(verb_id)
        if (verb_ids := context.user.readable_verbs) is not None:
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
            tuple(bindings),
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def all_at_dates(cls, target_dates, include_validity=False):
        """
        Yields tuples of (date, claims) for each target date.

        Target dates are strings of the shape "%m-%d", e.g. "05-01".
        For every target date we guarantee that we return a response, even if
        there are no claims.
        """
        cur = db.conn.cursor()
        conditions = [
            "v.data_type = 'date'",
        ]
        if not include_validity:
            conditions.extend([
                "v.id != ?",
                "v.id != ?",
            ])
        conditions.append(
            f"""({' OR '.join(f"c.value LIKE '%-{d}'" for d in target_dates)})"""
        )
        if (verb_ids := context.user.readable_verbs) is not None:
            conditions.append(
                f"verb_id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
            )

        query = f"""
            SELECT c.id
            FROM claims c
            LEFT JOIN verbs v ON c.verb_id = v.id
            WHERE {" AND ".join(conditions)}
        """
        results = {
            d: [] for d in target_dates
        }
        for row in cur.execute(
            query,
            () if include_validity else (
                VALID_FROM,
                VALID_UNTIL,
            ),
        ):
            claim = cls(row[0])
            results[claim.object.value[5:]].append(claim)

        for d in target_dates:
            yield d, results[d]

    @classmethod
    def all_with_value(cls, data_type, value, *, like=False, page_no=0, page_size=20):
        """
        Yields claims where the value is the given one.

        If `like` is true, comparisons are made with `LIKE` instead of `=`.
        """
        cur = db.conn.cursor()
        conditions = [
            "v.data_type = ?",
            "c.value LIKE ?",
        ]
        if (verb_ids := context.user.readable_verbs) is not None:
            conditions.append(
                f"verb_id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
            )

        query = f"""
            SELECT c.id
            FROM claims c
            LEFT JOIN verbs v ON c.verb_id = v.id
            WHERE {" AND ".join(conditions)}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
        """
        for row in cur.execute(
            query,
            (data_type, value),
        ):
            yield cls(row[0])

    def comments(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                c.id
            FROM claims c
            WHERE c.subject_id = ?
            AND c.verb_id = ?
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (self.id, COMMENT),
        ).fetchall():
            yield Claim(row["id"])

    def incoming_claims(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
        if (verb_ids := context.user.readable_verbs) is not None:
            cond = f"AND v.id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
        else:
            cond = ""
        for row in cur.execute(
            f"""
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE c.object_id = ?
            AND v.data_type <> 'undirected_link'
            {cond}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (self.id,),
        ).fetchall():
            yield Claim(row["id"])

    def incoming_mentions(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
        if (verb_ids := context.user.readable_verbs) is not None:
            cond = f"AND v.id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
        else:
            cond = ""
        for row in cur.execute(
            f"""
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE c.value LIKE '%[@' || ? || ']%' {cond}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (self.id,),
        ).fetchall():
            yield Claim(row["id"])

    def outgoing_claims(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
        if (verb_ids := context.user.readable_verbs) is not None:
            cond = f"AND v.id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
        else:
            cond = ""
        for row in cur.execute(
            f"""
            SELECT
                c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE (c.subject_id = ?
            OR (v.data_type = 'undirected_link' AND c.object_id = ?))
            {cond}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (self.id, self.id),
        ).fetchall():
            yield Claim(row["id"])

    def all_links(self, page_no=0, page_size=20):
        cur = db.conn.cursor()
        if (verb_ids := context.user.readable_verbs) is not None:
            cond = f"AND v.id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
        else:
            cond = ""
        for row in cur.execute(
            f"""
            SELECT
            c.id
            FROM claims c
            LEFT JOIN verbs v
            ON c.verb_id = v.id
            WHERE v.data_type LIKE '%directed_link'
            AND v.id != {IS_A}
            AND (c.subject_id = ? OR c.object_id = ?)
            {cond}
            """,
            (self.id, self.id),
        ).fetchall():
            yield Claim(row["id"])

    def outgoing_inferred_claims(self):
        inferables = Verb.get_inferables()
        for inferable in inferables:
            yield from inferable(self.id)

    @classmethod
    def all_labelled(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = db.conn.cursor()

        if (verb_ids := context.user.readable_verbs) is None:
            cond = ""
        else:
            cond = f"AND c.verb_id IN ({','.join(str(verb_id) for verb_id in verb_ids)})"
        for row in cur.execute(
            f"""
            SELECT
                c.id AS id
            FROM claims c
            WHERE c.verb_id = {ROOT} {cond}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def all_categories(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = db.conn.cursor()
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

    @classmethod
    def all_comments(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = db.conn.cursor()
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM claims c
            WHERE c.verb_id = ?
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            (COMMENT,),
        ).fetchall():
            yield cls(row["id"])

    def delete(self):
        cur = db.conn.cursor()
        cur.execute("DELETE FROM claims WHERE id = ?", (self.id,))
        cur.execute("DELETE FROM forward_index WHERE table_name = 'claims' AND id = ?", (self.id,))
        cur.execute("DELETE FROM inverted_index WHERE table_name = 'claims' AND id = ?", (self.id,))
        # evict deleted claim from cache:
        db.conn.commit()
        self._cache.pop(self.id, None)
        if self.subject and hasattr(Claim.get_data.__wrapped__, "_cached"):
            Claim.get_data.__wrapped__._cached.pop(self.subject.id, None)

    def set_value(self, value):
        cur = db.conn.cursor()
        if self.verb.data_type.name.endswith("directed_link"):
            cur.execute(
                """
                UPDATE claims
                SET object_id = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    value.id,
                    self.id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE claims
                SET value = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    value.encode(),
                    self.id,
                ),
            )
            if self.is_entity:
                update_index_for_doc(cur, "claims", self.id, value.encode())
        db.conn.commit()
        self.populate()

    def set_subject(self, subject):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE claims
            SET subject_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                subject.id,
                self.id,
            ),
        )
        db.conn.commit()
        self.populate()

    def set_verb(self, verb):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE claims
            SET verb_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                verb.id,
                self.id,
            ),
        )
        db.conn.commit()
        self.populate()

    @classmethod
    def new(cls, subject, verb, value_or_object):
        cur = db.conn.cursor()
        if verb.id in DATA_LABELS:
            fn = subject.get_data.__wrapped__
            if hasattr(fn, "_cached"):
                delattr(fn, "_cached")
            if verb.id == AVATAR:
                cur.execute(
                    """
                        DELETE FROM claims
                        WHERE subject_id = ? AND verb_id = ?
                    """,
                    (subject.id, verb.id),
                )
        if verb.data_type.name.endswith("directed_link"):
            # "entity"
            cur.execute(
                """
                    INSERT INTO claims
                        (subject_id, verb_id, object_id, owner_id)
                    VALUES
                        (?, ?, ?, ?)
                """,
                (subject.id, verb.id, value_or_object.id, context.user.id),
            )
        else:
            cur.execute(
                """
                INSERT INTO claims
                    (subject_id, verb_id, value, owner_id)
                VALUES
                    (?, ?, ?, ?)
                """,
                (subject.id, verb.id, value_or_object.encode(), context.user.id),
            )

        db.conn.commit()
        return Claim(cur.lastrowid)

    @classmethod
    def new_entity(cls, name):
        cur = db.conn.cursor()
        cur.execute(
            "INSERT INTO claims (verb_id, value, owner_id) VALUES (?, ?, ?)",
            (ROOT, name, context.user.id),
        )
        new_id = cur.lastrowid
        update_index_for_doc(cur, "claims", new_id, name)
        db.conn.commit()
        return Claim(new_id)

    @timed_cache(CLAIM_DATA_CACHE_TIME, key=lambda self, *_, **__: self.id)
    def get_data(self, claims=None):
        data = {}
        if claims is None:
            claims = Claim.all(subject_id=self.id)
        for cl in claims:
            if cl.verb.id in DATA_LABELS:
                data.setdefault(cl.verb.id, []).append(cl)
            if cl.verb.id not in (SOURCE, VALID_FROM, VALID_UNTIL):
                # A bit of a lie, but these verbs have special UI anyways so we
                # don't need to show that those claims exist.
                data["has_claims"] = True
        return data

    def _get_source(self, data):
        if SOURCE not in data:
            return "", ""
        src_id = f"--source-{self.id}"
        sources = []
        for source in data[SOURCE]:
            if sources:
                sources.append(H.br())
            sources.append(H(
                source.html("handle"),
                " ",
                source.object.html(),
            ))
        return H.button(
            "\N{SPEECH BALLOON}",
            cls="source-button",
            command="toggle-popover",
            commandfor=f"source-{self.id}",
            interestfor=f"source-{self.id}",
            style=f"anchor-name: {src_id};",
        ), H.div(
            *sources,
            id=f"source-{self.id}",
            popover="hint",
            cls="inline-source",
            style=f"position-anchor: {src_id};",
        )

    def _get_remarks(self, data):
        remarks = []
        css_classes = set()
        validity = self._is_valid(data)
        if validity is False:
            css_classes.add("invalid")
        elif validity is None:
            css_classes.add("invalid invalid-maybe")

        for valid_from in data.get(VALID_FROM, []):
            remarks.append(f"from {valid_from.object}")
        for valid_until in data.get(VALID_UNTIL, []):
            remarks.append(f"until {valid_until.object}")
        remarks.sort(key=lambda s: s.split()[-1])

        if remarks:
            remarks = {"data_tooltip": ", ".join(remarks)}
        else:
            remarks = {}
        return f" {' '.join(css_classes)}" if css_classes else "", remarks

    def _is_valid(self, data):
        today = date.today()
        before, after, during = [], [], []
        for validity_type in (VALID_FROM, VALID_UNTIL):
            for validity in data.get(validity_type, []):
                start, end = validity.object.value
                if end < today:
                    before.append((validity_type, validity.object.value))
                elif start > today:
                    after.append((validity_type, validity.object.value))
                else:
                    during.append((validity_type, validity.object.value))
        if during:
            return None  # unknowable
        if not before and not after:
            return True
        if before:
            latest_before = max(before, key=lambda t: t[1][-1])[0]
        else:
            latest_before = None
        if after:
            earliest_after = min(after, key=lambda t: t[1][0])[0]
        else:
            earliest_after = None

        return {
            (VALID_FROM, VALID_FROM): None,  # unclear which is correct
            (VALID_FROM, VALID_UNTIL): True,
            (VALID_FROM, None): True,
            (VALID_UNTIL, VALID_FROM): False,
            (VALID_UNTIL, VALID_UNTIL): None,  # unclear which is correct
            (VALID_UNTIL, None): False,
            (None, VALID_FROM): False,
            (None, VALID_UNTIL): True,
            (None, None): True,  # just for completeness; will be handled by short circuit earlier
        }[latest_before, earliest_after]

    @property
    def is_entity(self):
        return self.verb.id == ROOT

    def html(self, fmt=None):
        if not context.user.can("read", "verb", self.verb.id):
            return H("(unknown claim)")
        data = self.get_data()
        css_classes, remarks = self._get_remarks(data)
        source_button, source_popover = self._get_source(data)
        if fmt == "label":
            if self.is_entity and not context.user.redact:
                return H(self.object.value)
            else:
                return H(f"Claim #{self.id}")
        elif not fmt or fmt == "nested":
            if self.is_entity and not context.user.redact:
                return H.a(
                    self.html("avatarsmall"),
                    escape(self.object.value),
                    **remarks,
                    cls=f"claim-link{css_classes}",
                    href=self.url(),
                )
            elif self.is_entity:
                return H.a(
                    self.html("avatarsmall"),
                    f"Claim #{self.id}",
                    **remarks,
                    cls=f"claim-link{css_classes}",
                    href=self.url(),
                )
            elif fmt == "nested":
                return H.span(
                    self.html("handle"),
                    self.subject.html("nested"),
                    " ",
                    self.verb.html("nested"),
                    " ",
                    self.object.html("nested"),
                    cls=f"svo nested{css_classes}",
                    **remarks,
                )
            else:
                return H(
                    H.span(
                        self.html("handle"),
                        self.subject.html("nested"),
                        " ",
                        self.verb.html("nested"),
                        " ",
                        self.object.html("nested"),
                        source_button,
                        cls=f"svo{css_classes}",
                        **remarks,
                    ),
                    source_popover,
                )
        elif fmt == "input-widget-ref":
            if self.is_entity and not context.user.redact:
                return H.span(
                    self.html("avatarsmall"),
                    escape(self.object.value),
                    contenteditable="false",
                    data_claim_ref=str(self.id),
                    cls="input-widget-ref",
                )
            else:
                return H.span(
                    f"Claim #{self.id}",
                    contenteditable="false",
                    data_claim_ref=str(self.id),
                    cls="input-widget-ref",
                )
        elif fmt == "heading":
            if context.user.can("write", "verb", IS_A):
                new_cat = H.span(
                    ", +",
                    cls="clickable new-cat",
                    hx_get=f"/claims/new/verb?verb={IS_A}&claim_ids={self.id}&direction=outgoing&standalone=1",
                    hx_target="#edit-area",
                )
            else:
                new_cat = None
            if IS_A in data:
                cat = H(
                    H.br(),
                    H.small(
                        "&lt;",
                        *join(",", (H.span(c.html("handle"), c.object.html()) for c in data[IS_A])),
                        new_cat,
                        "&gt;",
                        cls="cats",
                    ),
                )
            else:
                cat = H(
                    H.br(),
                    H.small(
                        "&lt;",
                        new_cat,
                        "&gt;",
                        cls="cats",
                    ),
                )
            if self.is_entity:
                if context.user.redact:
                    text = f"Claim #{self.id}"
                else:
                    text = escape(self.object.value)
                if LATLON in data:
                    latlons = H(
                        H.br(),
                        *(
                            H.small(
                                H.a(
                                    HANDLE,
                                    cls="handle",
                                    href=latlon.url(),
                                ),
                                H.a(
                                    "\N{PUSHPIN}",
                                    href=S.location_link_template.format(quote_plus(latlon.object.value)),
                                ),
                                cls="latlon",
                            )
                            for latlon in data[LATLON]
                        ),
                    )
                else:
                    latlons = None
                return H.h2(text, cat, latlons)
            else:
                return H.h2(self.html())
        elif fmt.startswith("vo:"):
            subj_id = int(fmt[3:])
            # Handle undirected links properly (always display the _other_ claim)
            if self.subject.id == subj_id:
                return H(
                    H.span(
                        self.html("handle"),
                        self.verb.html(),
                        " ",
                        self.object.html(),
                        source_button,
                        **remarks,
                        cls=f"vo{css_classes}",
                    ),
                    source_popover,
                )
            else:
                return H(
                    H.span(
                        self.html("handle"),
                        self.verb.html(),
                        " ",
                        self.subject.html(),
                        source_button,
                        **remarks,
                        cls=f"vo{css_classes}",
                    ),
                    source_popover,
                )
        elif fmt == "sv":
            return H(
                H.span(
                    self.html("handle"),
                    self.subject.html(),
                    " ",
                    self.verb.html(),
                    source_button,
                    **remarks,
                    cls=f"sv{css_classes}",
                ),
                source_popover,
            )
        elif fmt == "handle":
            return H.a(
                HANDLE,
                cls=f"handle{' more' if 'has_claims' in data else ''}",
                href=self.url(),
            )
        elif fmt == "avatarsmall":
            if AVATAR not in data or context.user.redact:
                return None
            return H.img(src=self.url("avatar"), cls="avatar")
        elif fmt == "avatar":
            if AVATAR not in data:
                return None
            return H.img(src=self.url("avatar"), cls="avatar", alt="avatar")
        elif fmt == "raw":
            if context.user.redact:
                return f"Claim #{self.id}"
            return escape(self.object.value)
        elif fmt == "comment":
            if context.user.redact:
                text = "..."
            else:
                text = escape(self.object.value)
            return H.tr(
                H.td(
                    self.owner.html(),
                    ":",
                    data_placement="right",
                    data_tooltip=str(self.created_at),
                    cls="comment-author",
                ),
                H.td(self.html("handle")),
                H.td(text, cls="comment-text"),
            )
        elif fmt == "rename":
            if self.verb.id == ROOT and (context.user.is_admin or self.owner.id == context.user.id):
                return H.a(
                    "Rename ",
                    H.i("\N{LOWER RIGHT PENCIL}"),
                    hx_get=self.url("edit"),
                    hx_target="#edit-area",
                )
            else:
                return H.a(
                    "Rename ",
                    H.i("\N{LOWER RIGHT PENCIL}"),
                    disabled=True,
                )
        elif fmt == "hamburger":
            parts = []
            if self.verb.id == ROOT:
                parts.append(H.li(self.html("rename")))
                parts.append(H.li(H.a("Network ", H.i("\N{SPIDER WEB}\ufe0e"), href=self.url("network"))))
            if not self.is_entity:
                if context.user.is_admin or self.owner.id == context.user.id:
                    parts.append(
                        H.li(
                            H.a(
                                "Edit subject ",
                                H.i("\N{RIGHTWARDS ARROW}"),
                                hx_target="#edit-area",
                                hx_get=self.url("move"),
                            ),
                        )
                    )
                    parts.append(
                        H.li(
                            H.a(
                                "Edit verb ",
                                H.i("\N{RIGHTWARDS ARROW}"),
                                hx_target="#edit-area",
                                hx_get=self.url("reverb"),
                            ),
                        )
                    )
                    parts.append(
                        H.li(
                            H.a(
                                "Edit object ",
                                H.i("\N{LOWER RIGHT PENCIL}"),
                                hx_target="#edit-area",
                                hx_get=self.url("edit"),
                            ),
                        )
                    )
                if context.user.can("write", "verb", SOURCE):
                    parts.append(
                        H.li(
                            H.a(
                                "Source ",
                                H.i("\N{SPEECH BALLOON}\ufe0e"),
                                hx_target="#edit-area",
                                hx_get=f"/claims/new/verb?verb={SOURCE}&claim_ids={self.id}&direction=outgoing&standalone=1",
                            ),
                        )
                    )
                if context.user.can("write", "verb", VALID_FROM):
                    parts.append(
                        H.li(
                            H.a(
                                "Valid from ",
                                H.i("\N{LEFTWARDS ARROW TO BAR}"),
                                hx_target="#edit-area",
                                hx_get=f"/claims/new/verb?verb={VALID_FROM}&claim_ids={self.id}&direction=outgoing&standalone=1",
                            ),
                        )
                    )
                if context.user.can("write", "verb", VALID_UNTIL):
                    parts.append(
                        H.li(
                            H.a(
                                "Valid until ",
                                H.i("\N{RIGHTWARDS ARROW TO BAR}"),
                                hx_target="#edit-area",
                                hx_get=f"/claims/new/verb?verb={VALID_UNTIL}&claim_ids={self.id}&direction=outgoing&standalone=1",
                            ),
                        )
                    )
            else:
                if context.user.can("write", "verb", AVATAR):
                    parts.append(
                        H.li(
                            H.a(
                                "Set avatar ",
                                H.i("\N{FRAME WITH PICTURE}\ufe0e"),
                                hx_target="#edit-area",
                                hx_get=f"/claims/new/verb?verb={AVATAR}&claim_ids={self.id}&direction=outgoing&standalone=1",
                            ),
                        )
                    )
                if context.user.can("write", "verb", LATLON):
                    parts.append(
                        H.li(
                            H.a(
                                "Set location ",
                                H.i("\N{PUSHPIN}\ufe0e"),
                                hx_target="#edit-area",
                                hx_get=f"/claims/new/verb?verb={LATLON}&claim_ids={self.id}&direction=outgoing&standalone=1",
                            ),
                        )
                    )
            if (context.user.is_admin or self.owner.id == context.user.id) and self.deletable:
                parts.append(
                    H.li(
                        H.a(
                            "Delete ",
                            H.i("\N{WASTEBASKET}\ufe0e"),
                            hx_target="#edit-area",
                            hx_delete=self.url(),
                            hx_confirm="Are you sure you want to delete this claim?",
                        ),
                    )
                )
            if not parts:
                return None
            return H.details(
                H.summary("\N{TRIGRAM FOR HEAVEN}"),
                H.ul(
                    *parts,
                    dir="rtl",
                ),
                cls="dropdown hamburger",
            )
        return f"TODO: {fmt!r}"

    @property
    def deletable(self):
        return (
            not list(self.outgoing_claims())
            and not list(self.incoming_claims())
            and not list(self.incoming_mentions())
        )

    def __str__(self):
        tags = self.html()
        if tags:
            return "".join(tags.serialize())
        return ""

    def graph_elements(self, verbs=None):
        data = self.get_data()
        node = {
            "label": str(self.html("label")).replace('"', "'"),
            "id": str(self.id),
            "cat": data[IS_A][0].object.id if data.get(IS_A) else None,
        }
        edges = []
        for link in self.outgoing_claims(page_size=999):
            if not link.verb.data_type.name.endswith("directed_link"):
                continue
            if verbs and link.verb not in verbs:
                continue
            if self.id == link.object.id:
                continue
            if link.verb.id in (IS_A, ROOT):
                continue
            edge_label = link.verb.label.replace('"', "'")
            if not link._is_valid(link.get_data()):
                edge_label = f"({edge_label})"
            edges.append(
                {
                    "source": str(self.id),
                    "target": str(link.object.id),
                    "label": edge_label,
                    "type": "arrow" if link.verb.data_type.name == "directed_link" else "line",
                }
            )
        return node, edges

    def merge(self, other):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE claims
            SET subject_id=?
            WHERE subject_id = ?
            """,
            (self.id, other.id),
        )
        cur.execute(
            """
            UPDATE claims
            SET object_id=?
            WHERE object_id = ?
            """,
            (self.id, other.id),
        )
        for mention in other.incoming_mentions(page_size=999):
            value = mention.object
            value.value = re.sub(rf"<@{other.id}>", f"<@{self.id}>", value.value)
            mention.set_value(value)
        cur.execute(
            """
            DELETE FROM claims
            WHERE id = ?
            """,
            (other.id,),
        )
        db.conn.commit()

    @classmethod
    def stats(cls):
        res = Counter()
        res["verbs"] = Counter()
        res["categories"] = {}
        cur = db.conn.cursor()
        for row in cur.execute("SELECT COUNT(*) AS count, verb_id FROM claims GROUP BY verb_id").fetchall():
            res["total"] += row["count"]
            res["verbs"][row["verb_id"]] += row["count"]
        for row in cur.execute("SELECT COUNT(object_id) AS count, object_id AS category_id FROM claims WHERE verb_id = -3 GROUP BY object_id").fetchall():
            res["categories"][row["category_id"]] = row["count"]
        return res


class Query(Model):
    table_name = "queries"
    fields = (
        "label",
        "sql",
    )

    def populate(self):
        cur = db.conn.cursor()
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
    def all(cls, *, order_by="id ASC", page_no=0, page_size=20):
        cur = db.conn.cursor()
        conditions = ["1=1"]
        if (query_ids := context.user.viewable_queries) is not None:
            conditions.append(
                f"id IN ({','.join(str(query_id) for query_id in query_ids)})"
            )
        for row in cur.execute(
            f"""
            SELECT
                id
            FROM queries
            WHERE {" AND ".join(conditions)}
            ORDER BY {order_by}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """
        ).fetchall():
            yield cls(row["id"])

    @classmethod
    def new(cls, label, sql):
        cur = db.conn.cursor()
        cur.execute("INSERT INTO queries (label, sql) VALUES (?, ?)", (label, sql))
        q_id = cur.lastrowid
        update_index_for_doc(cur, "queries", q_id, label)
        db.conn.commit()
        return cls(q_id)

    def rename(self, label):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE queries
            SET label=?
            WHERE id = ?
            """,
            (label, self.id),
        )
        db.conn.commit()
        self.label = label

    def html(self, fmt=None):
        if fmt == "heading":
            return H.h2(self.label)
        elif fmt == "hamburger":
            parts = []
            if context.user.is_admin:
                parts.append(
                    H.li(H.a(H.i("\N{LOWER RIGHT PENCIL}"), " Edit", href=self.url("edit")))
                )
                parts.append(
                    H.li(H.a(
                        H.i("\N{ERASE TO THE LEFT}"),
                        " Delete",
                        hx_delete=self.url(),
                        hx_confirm="Are you sure you want to delete this query?",
                        cls="danger",
                    ))
                )
            if parts:
                return H.details(
                    H.summary("\N{TRIGRAM FOR HEAVEN}"),
                    H.ul(
                        *parts,
                        dir="rtl",
                    ),
                    cls="dropdown hamburger",
                )
        else:
            return H.a(
                H.strong(self.label),
                cls="clickable query",
                hx_push_url="true",
                href=self.url(),
                hx_select="#container",
                hx_target="#container",
                hx_swap="outerMorph",
            )
        return None

    def run(self, bindings, *, page_no, page_size):
        cur = db.conn.cursor()
        cur.execute(
            f"""
            {self.prepared_sql}
            LIMIT {page_size}
            OFFSET {page_no * page_size}
            """,
            bindings,
        )
        return cur.fetchall()

    def bind(self, form):
        """
        Yields (name, form_element, value) triples.

        form_element is HTML for the input, including the value (if given).
        """
        form_elements = []
        bindings = []
        for i, match in enumerate(re.findall(r"\?\(([^)]+)\)", self.sql)):
            type, _, label = match.partition(" ")
            assert label.startswith("'") and label.endswith("'")
            value = form.get(f"v{i}")
            if value is not None:
                if type in ("verb",) or type.startswith("verb:"):
                    value = int(value)
                bindings.append(value)
            form_elements.append(self._build_form_input(i, label[1:-1], type, value, self.url()))
        return form_elements, tuple(bindings) if len(bindings) == len(form_elements) else None

    def _build_form_input(self, i, label, type, value, url):
        if type == "string":
            return H.label(
                label,
                H.input(
                    hx_get=url,
                    hx_target="#queryresults",
                    hx_select="#queryresults",
                    hx_swap="outerMorph",
                    name=f"v{i}",
                    value=str(value or ''),
                )
            )
        elif type == "verb" or type.startswith("verb:"):
            *_, data_type = type.partition(":")
            verbs = Verb.all(page_size=9999, **({"data_type": data_type} if data_type else {}))
            return H.label(
                label,
                H.select(
                    H.option("--Verb--", selected=True, disabled=True),
                    *(
                        H.option(
                            f"{verb.label} ({verb.data_type})",
                            value=str(verb.id),
                            selected=value is not None and int(value) == verb.id,
                        )
                        for verb in verbs
                        if verb.id >= 0 and verb.data_type is not TYPES["inferred"]
                    ),
                    hx_get=url,
                    hx_target="#queryresults",
                    hx_select="#queryresults",
                    hx_swap="outerMorph",
                    name=f"v{i}",
                ),
            )
        raise RuntimeError(f"Unknown type {type}")

    @property
    def prepared_sql(self):
        return re.sub(r"\?\([^)]+\)", "?", self.sql)

    def update(self, sql, label):
        cur = db.conn.cursor()
        cur.execute(
            """
            UPDATE queries
            SET label=?, sql=?
            WHERE id=?
            """,
            (label, sql, self.id),
        )
        db.conn.commit()
        self.sql = sql
        self.label = label

    def delete(self):
        cur = db.conn.cursor()
        cur.execute("DELETE FROM queries WHERE id = ?", (self.id,))
        cur.execute(
            "DELETE FROM permissions WHERE object = ? AND permission = 'view-query'",
            (self.id,),
        )
        db.conn.commit()
        # evict deleted query from cache:
        self._cache.pop(self.id, None)


    def __str__(self):
        tags = self.html()
        if tags:
            return "".join(tags.serialize())
        return ""


class User(Model):
    table_name = "users"
    fields = (
        "name",
        "hash",
        "entity",
        "is_admin",
        "salt",
        "permissions",
        "generation",
        "redact",
        "last_session_at",
    )

    def populate(self):
        cur = db.conn.cursor()
        row = cur.execute(
            """
                SELECT
                    id, name, hash, entity_id, is_admin, salt, generation, redact, last_session_at
                FROM users
                WHERE id = ?
            """,
            (self.id,),
        ).fetchone()
        if not row:
            raise ValueError("No User with this ID found")
        self.name = row["name"]
        self.hash = row["hash"]
        self.salt = row["salt"]
        self.is_admin = row["is_admin"]
        self.redact = row["redact"]
        self.generation = row["generation"]
        if row["entity_id"]:
            self.entity = Claim(row["entity_id"])
        else:
            self.entity = None
        if row["last_session_at"]:
            self.last_session_at = datetime.fromisoformat(row["last_session_at"])
        else:
            self.last_session_at = None
        if not self.is_admin:
            self.permissions = set()
            for row in cur.execute(
                """
                    SELECT
                        permission, object
                    FROM permissions
                    WHERE user_id = ?
                """,
                (self.id,),
            ).fetchall():
                self.permissions.add((row["permission"], row["object"]))
            # internal verbs can always be seen
            for internal_verb in DATA_LABELS:
                self.permissions.add(("read-verb", internal_verb))
        else:
            self.permissions = None  # all of them
        if "readable_verbs" in self.__dict__:
            del self.readable_verbs
        if "writable_verbs" in self.__dict__:
            del self.writable_verbs
        if "viewable_queries" in self.__dict__:
            del self.viewable_queries

    @classmethod
    def by_name(cls, name):
        cur = db.conn.cursor()
        row = cur.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
        if not row:
            raise ValueError("No User with this ID found")
        return cls(row["id"])

    @classmethod
    def new(cls, *, name, password, readable_verbs, writable_verbs, viewable_queries, redact, entity_id):
        cur = db.conn.cursor()
        hash, salt = hash_password(password)
        cur.execute(
            "INSERT INTO users (name, hash, salt, is_admin, redact, entity_id) VALUES (?, ?, ?, ?, ?, ?)",
            (name, hash, salt, 0, redact, entity_id),
        )
        u_id = cur.lastrowid
        for readable_verb in readable_verbs:
            cur.execute(
                "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                (u_id, "read-verb", readable_verb),
            )
        for writable_verb in writable_verbs:
            cur.execute(
                "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                (u_id, "write-verb", writable_verb),
            )
        for viewable_query in viewable_queries:
            cur.execute(
                "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                (u_id, "view-query", viewable_query),
            )
        db.conn.commit()
        return cls(u_id)

    def update(self, *, name, password, readable_verbs, writable_verbs, viewable_queries, redact, entity_id):
        cur = db.conn.cursor()
        to_set, values = ["redact=?"], [redact]
        if name != self.name:
            to_set.append("name=?")
            values.append(name)
        if password:
            self.increment_generation(skip_populate=True)
            hash, salt = hash_password(password)
            to_set.append("hash=?")
            values.append(hash)
            to_set.append("salt=?")
            values.append(salt)
        if entity_id:
            to_set.append("entity_id=?")
            values.append(int(entity_id))
        values.append(self.id)
        if to_set:
            cur.execute(
                f"UPDATE users SET {', '.join(to_set)} WHERE id=?", tuple(values)
            )

        if not self.is_admin:
            if any(vid >= 0 for vid in set(readable_verbs) ^ {verb for perm, verb in self.permissions if perm == "read-verb"}):
                cur.execute("DELETE FROM permissions WHERE user_id = ? AND permission = 'read-verb'", (self.id,))
                for readable_verb in readable_verbs:
                    cur.execute(
                        "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                        (self.id, "read-verb", readable_verb),
                    )
            if set(writable_verbs) ^ {verb for perm, verb in self.permissions if perm == "write-verb"}:
                cur.execute("DELETE FROM permissions WHERE user_id = ? AND permission = 'write-verb'", (self.id,))
                for writable_verb in writable_verbs:
                    cur.execute(
                        "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                        (self.id, "write-verb", writable_verb),
                    )
            if set(viewable_queries) ^ {query for perm, query in self.permissions if perm == "view-query"}:
                cur.execute("DELETE FROM permissions WHERE user_id = ? AND permission = 'view-query'", (self.id,))
                for viewable_query in viewable_queries:
                    cur.execute(
                        "INSERT INTO permissions (user_id, permission, object) VALUES (?, ?, ?)",
                        (self.id, "view-query", viewable_query),
                    )
        db.conn.commit()
        self.populate()

    def html(self, fmt=None):
        if fmt == "link":
            if self.entity:
                return H(
                    self.entity.html(),
                    " (",
                    H.a(
                        self.name,
                        href=self.url(),
                    ),
                    ")",
                )
            return H.a(self.name, href=self.url())
        elif fmt == "session":
            if not self.last_session_at:
                return H("no active session")
            else:
                delta = datetime.now() - self.last_session_at
                if delta.days == 0:
                    if delta > timedelta(hours=1):
                        diff = f"{round(delta / timedelta(hours=1))} hours ago"
                    else:
                        diff = f"{round(delta / timedelta(minutes=1))} minutes ago"
                else:
                    diff = date.today() - NonOmniscientDate(str(self.last_session_at.date()))
                if delta > SESSION_MAX_AGE:
                    delta = f"{delta} (expired)"
                return H(f"last refreshed {diff}")
            return str(type(self.last_session_at).__name__) + str(self.last_session_at)
        elif fmt == "hamburger":
            return H.details(
                H.summary("\N{TRIGRAM FOR HEAVEN}"),
                H.ul(
                    H.li(
                        H.a(
                            H.i("\N{LOWER RIGHT PENCIL}"),
                            " Edit",
                            href=self.url("edit"),
                        ),
                    ),
                    H.li(
                        H.a(
                            H.i("\N{WASTEBASKET}\ufe0e"),
                            " Delete",
                            cls="danger",
                            disabled=True,
                        ),
                    ),
                    dir="rtl",
                ),
                cls="dropdown hamburger",
            )
        elif fmt == "label":
            if self.entity:
                return self.entity.html("label")
            return H(self.name)
        if self.entity:
            return self.entity.html()
        return H(self.name)

    def __str__(self):
        tags = self.html()
        if tags:
            return "".join(tags.serialize())
        return ""

    @property
    def payload(self):
        return {
            "u": self.id,
            "t": f"{datetime.now():%Y-%m-%dT%H:%M}",
            "g": self.generation,
        }

    def increment_generation(self, skip_populate=False):
        cur = db.conn.cursor()
        cur.execute(
            "UPDATE users SET generation = generation + 1 WHERE id = ?",
            (self.id,),
        )
        db.conn.commit()
        if not skip_populate:
            self.populate()

    def can(self, do, what, whom):
        if self.is_admin:
            return True
        return (f"{do}-{what}", whom) in self.permissions

    @cached_property
    def readable_verbs(self):
        if self.is_admin:
            return None
        return {verb_id for perm, verb_id in self.permissions if perm == "read-verb"}

    @cached_property
    def writable_verbs(self):
        if self.is_admin:
            return None
        return {verb_id for perm, verb_id in self.permissions if perm == "write-verb"}

    @cached_property
    def viewable_queries(self):
        if self.is_admin:
            return None
        return {query_id for perm, query_id in self.permissions if perm == "view-query"}

    def make_session(self, response):
        response.add_cookie(
            "session",
            sign(self.payload),
            secure=True,
            httponly=True,
            samesite="Strict",
            max_age=int(SESSION_MAX_AGE.total_seconds()),
        )
        cur = db.conn.cursor()
        cur.execute(
            "UPDATE users SET last_session_at = ? WHERE id = ?",
            (datetime.now(), self.id),
        )
        db.conn.commit()
        self.populate()


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

    def html(self, fmt=None):
        return self.prop.data_type.display_html(self.value, prop=self.prop, fmt=fmt)

    def __str__(self):
        tags = self.html()
        if tags:
            return "".join(tags.serialize())
        return ""


class Inferable:
    def __init__(self, verb):
        self.verb = verb

    def _get_condition_variants(self, conditions):
        if not conditions:
            yield []
            return

        [ci, cs, cv, co], *rest = conditions
        for variant in self._get_condition_variants(rest):
            yield [conditions[0], *variant]
        if Verb(int(cv)).data_type is TYPES["undirected_link"]:
            for variant in self._get_condition_variants(rest):
                yield [(ci, co, cv, cs), *variant]

    @cached_property
    def sql_query(self):
        extra = json.loads(self.verb.extra)
        conditions = []
        for n in count(start=1):
            if f"g{n}s" not in extra:
                break
            subj = extra[f"g{n}s"]
            verb_id = int(extra[f"g{n}v"])
            obj = extra[f"g{n}o"]

            conditions.append((n, subj, verb_id, obj))

        graph = {}
        for c1, c2 in combinations(conditions, 2):
            if {c1[1], c1[3]} & {c2[1], c2[3]}:  # shared references
                graph.setdefault(min(c1[0], c2[0]), set()).add(max(c1[0], c2[0]))

        new_conditions = []
        for n in graphlib.TopologicalSorter(graph).static_order():
            new_conditions.append(conditions[n-1])

        conditions = new_conditions

        parts = []

        for conditions in self._get_condition_variants(conditions):
            links = []
            joins = []
            for i, condition in enumerate(conditions):
                if not i:
                    # can't link at the first condition
                    continue
                my_names = {condition[1], condition[3]}
                for other in conditions[:i]:  # needs to connect somehow with a _previous_ condition
                    if my_names & {other[1], other[3]}:
                        links.append((condition, other))
                        break
                else:
                    raise RuntimeError  # we didn't find a link
            for (s_id, s_sub, _, s_obj), (t_id, t_sub, _, t_obj) in links:
                if s_sub == t_sub:
                    joins.append((s_id, f"cond{s_id}.subject_id = cond{t_id}.subject_id"))
                elif s_sub == t_obj:
                    joins.append((s_id, f"cond{s_id}.subject_id = cond{t_id}.object_id"))
                elif s_obj == t_sub:
                    joins.append((s_id, f"cond{s_id}.object_id = cond{t_id}.subject_id"))
                elif s_obj == t_obj:
                    joins.append((s_id, f"cond{s_id}.object_id = cond{t_id}.object_id"))

            parts.append(self._build_subquery(conditions, joins))
        return " UNION ".join(parts)

    def __call__(self, claim_id):
        cur = db.conn.cursor()
        for row in cur.execute(self.sql_query, {"this": claim_id}).fetchall():
            yield InferredClaim(Claim(claim_id), self.verb, Claim(row["id"]))

    def _build_subquery(self, conditions, joins):
        labels = {}
        for cid, slab, _, olab in conditions:
            labels[slab] = f"cond{cid}.subject_id"
            labels[olab] = f"cond{cid}.object_id"
        parts = [
            f"SELECT DISTINCT({labels['that']}) AS id FROM claims cond{conditions[0][0]}"
        ]
        for cond_id, db_join in joins:
            parts.append(f"LEFT JOIN claims cond{cond_id} ON {db_join}")
        parts.append(f"WHERE {labels['this']}=:this")
        for cond_id, sname, vid, oname in conditions:
            parts.append(f"AND cond{cond_id}.verb_id = {vid}")
        for lab_a, lab_b in combinations(labels, 2):
            parts.append(f"AND {labels[lab_a]} != {labels[lab_b]}")
        return " ".join(parts)


class InferredClaim:
    def __init__(self, subj, verb, obj):
        self.subject = subj
        self.verb = verb
        self.object = obj

    def html(self, fmt=None):
        if fmt == "handle":
            return None
        return Claim.html(self, fmt)

    def get_data(self):
        return {}

    def _get_remarks(self, data):
        return "", {}

    def _get_source(self, data):
        return "", ""
