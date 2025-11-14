import typing

from veronique.db import conn

UNKNOWN = object()

class Setting:
    def __init__(self, default):
        self.value = UNKNOWN
        self.default = default
        self.name = None
        self.converter = str

    def __get__(self, _obj, _objtype=None):
        if self.value is UNKNOWN:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (self.name,)).fetchone()
            if row is None:
                self.value = self.default
            else:
                self.value = self.converter(row["value"])
        return self.value

    def __set__(self, _obj, value):
        if value is None:
            value = self.default
        self.value = self.converter(value)
        row = conn.execute("SELECT value FROM settings WHERE key=?", (self.name,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (self.name, value))
        else:
            conn.execute("UPDATE settings SET value=? WHERE key=?", (value, self.name))
        conn.commit()

    def __set_name__(self, owner, name):
        self.converter = typing.get_type_hints(owner).get(name, str)
        self.name = name

class Settings:
    app_name: str = Setting("Véronique")
    page_size: int = Setting(20)
    index_days_ahead: int = Setting(7)
    index_days_back: int = Setting(3)


settings = Settings()
