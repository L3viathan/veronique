import ast
import operator
import typing

from veronique import db
from veronique.context import context
from veronique.constants import (
    SEARCH_DEFAULT_K1,
    SEARCH_DEFAULT_B,
    SEARCH_DEFAULT_N,
    INDEX_DEFAULT_TYPE,
    INDEX_DEFAULT_DAYS_AHEAD,
    INDEX_DEFAULT_DAYS_BACK,
    INDEX_DEFAULT_RECENT_EVENTS_MOD,
    DEFAULT_PHONE_REGION,
    DEFAULT_APP_NAME,
    DEFAULT_PAGE_SIZE,
)

UNKNOWN = object()

class ConditionalInt:
    """
    <10:1,<100:5,10

    meaning: if the given number is less than 10, 1. If it's less than 100, 5.
             otherwise 10.
    """
    def __init__(self, value):
        self._repr = str(value)
        self.checks = []
        for part in self._repr.split(","):
            cond, _, val = part.rpartition(":")
            val = int(val)
            def check(x, cond=cond):
                if cond:
                    op, checkval = cond[0], cond[1:]
                    return {
                        "<": operator.lt,
                        ">": operator.gt,
                        "=": operator.eq,
                    }[op](x, int(checkval))
                    return ast.literal_eval(f"{x}{cond}")
                return True
            self.checks.append((check, val))

    def __str__(self):
        return self._repr

    def __call__(self, value):
        for cond, res in self.checks:
            if cond(value):
                return res


class Setting:
    def __init__(self, default, user_settable=False):
        self.value = UNKNOWN
        self.default = default
        self.name = None
        self.converter = str
        self.user_settable = user_settable

    def __get__(self, _obj, _objtype=None):
        if self.value is UNKNOWN:
            row = db.conn.execute(
                "SELECT value FROM settings WHERE key=?",
                (self.key,),
            ).fetchone()
            if row is None:
                self.value = self.default
            else:
                self.value = self.converter(row["value"])
        return self.value

    def __set__(self, _obj, value):
        if value is None:
            value = self.default
        self.value = self.converter(value)
        row = db.conn.execute("SELECT value FROM settings WHERE key=?", (self.key,)).fetchone()
        if row is None:
            db.conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (self.key, str(value)))
        else:
            db.conn.execute("UPDATE settings SET value=? WHERE key=?", (str(value), self.key))
        db.conn.commit()

    def __set_name__(self, owner, name):
        self.converter = typing.get_type_hints(owner).get(name, str)
        self.name = name

    @property
    def key(self):
        if self.user_settable:
            return f"{self.name}:{context.user.name}"
        return self.name

class Settings:
    app_name: str = Setting(DEFAULT_APP_NAME)
    page_size: int = Setting(DEFAULT_PAGE_SIZE, user_settable=True)
    index_type: str = Setting(INDEX_DEFAULT_TYPE, user_settable=True)
    index_days_ahead: int = Setting(INDEX_DEFAULT_DAYS_AHEAD, user_settable=True)
    index_days_back: int = Setting(INDEX_DEFAULT_DAYS_BACK, user_settable=True)
    index_recent_events_mod: ConditionalInt = Setting(INDEX_DEFAULT_RECENT_EVENTS_MOD, user_settable=True)
    default_phone_region: str = Setting(DEFAULT_PHONE_REGION, user_settable=True)
    search_k_1: float = Setting(SEARCH_DEFAULT_K1)
    search_b: float = Setting(SEARCH_DEFAULT_B)
    search_n: int = Setting(SEARCH_DEFAULT_N)


settings = Settings()
