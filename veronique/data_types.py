import re
import json
import datetime
from itertools import count
from random import randint
import unicodedata
from datetime import date as dt_date, timedelta
from urllib.parse import quote_plus
from html import escape

import phonenumbers
from markdown_it import MarkdownIt

from veronique.nomnidate import NonOmniscientDate
from veronique.context import context
from veronique.settings import settings as S

TYPES = {}
TEXT_REF = re.compile(r"&lt;@(\d+)&gt;")
COORDS = re.compile(r"^-?\d+(.\d+)?, ?-?\d+(.\d+)?$")


def float_int(val):
    val = float(val)
    if val.is_integer():
        val = int(val)
    return val


class DataType:
    can_turn_into = ()

    def __init_subclass__(cls):
        TYPES[cls.__name__] = cls()

    def display_html(self, value, **_):
        return f"placeholder, not implemented for data type {type(self).__name__}."

    def input_html(self, value=None, **_):
        return f"placeholder, not implemented for data type {type(self).__name__}."

    def next_step(self, args):
        return None

    def get_extra(self, args):
        return None

    def encode(self, value):
        """Encode how value should be represented in the DB."""
        return str(value)

    def decode(self, encoded):
        """Decode from string in database to desired value."""
        return str(encoded)

    def extract_value(self, form):
        """
        Given a form object, extract the value in the form we want it.

        Typically, this is just whatever is in the value field, but this can be
        used to implement widgets with several <input>s.
        """
        return form.get("value")

    def detail_for(self, verb):
        return ""

    def __str__(self):
        return f"<em>{self.name}</em>"

    @property
    def name(self):
        return type(self).__name__

    @property
    def compatible_types(self):
        return {self.name, *self.can_turn_into}


class directed_link(DataType):
    def input_html(self, value=None, claim_id=None, direction=None, verb_id=None, allow_connect=True, **_):
        return f"""
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="Start typing..."
                    hx-get="/claims/autocomplete{f"?connect={claim_id}:{direction}:{verb_id}" if allow_connect else ""}"
                    hx-target="next .ac-results"
                    hx-swap="innerHTML"
                    hx-trigger="input changed delay:200ms, search"
                >
                <div class="ac-results">
                </div>
            </div>
        """


class undirected_link(directed_link):
    pass


class inferred(DataType):
    def next_step(self, args):
        import veronique.objects as O
        hxall = 'hx-select="#autoform" hx-replace="outerHTML" hx-target="#autoform" hx-get="/verbs/new/steps" hx-include="closest form"'
        verbs = list(O.Verb.all(data_type="%directed_link", page_size=999))
        if "g1s" not in args:
            conditions = [("this", verbs[0].id, "that")]
        else:
            n = 1
            conditions = []
            while f"g{n}s" in args:
                conditions.append((args[f"g{n}s"], int(args[f"g{n}v"]), args[f"g{n}o"]))
                n += 1

        if "more" in args:
            conditions.append(("this", verbs[0].id, "that"))
        elif "less" in args:
            conditions.pop()

        alphabet = {"this", "that"}
        alphabet.update(s for s, *_ in conditions)
        alphabet.update(o for *_, o in conditions)
        alphabet.add(next(letter for letter in "ABCDEFG" if letter not in alphabet))
        alphabet = sorted(alphabet, key=lambda s: (s.isupper(), s.startswith("tha"), s))

        label = args.get("label", "")

        parts = [f"""
            <div id="autoform">
            <p>There will be a new relation
    <span class="svo"><tt class="claim-link">this</tt><span class="inline verb">{label}</span><tt class="claim-link">that</tt></span> if:
        """]

        for n, (subj, selected_verb_id, obj) in enumerate(conditions, start=1):
            parts.append(
                f"""
                <fieldset role="group">
                    <select name="g{n}s" {hxall}>
                """
            )
            for symbol in alphabet:
                parts.append(f"<option {'selected' if symbol == args.get(f'g{n}s') else ''}>{symbol}</option>")
            parts.append(
                f"""
                </select>
                <select name="g{n}v" {hxall}>
                """
            )
            for verb in verbs:
                parts.append(f"""
                    <option value="{verb.id}" {"selected" if verb.id == selected_verb_id else ""}>{verb.label}</option>
                """)
            parts.append(
                f"""
                    </select>
                    <select name="g{n}o" {hxall}>
                """
            )
            for symbol in alphabet:
                parts.append(f"<option {'selected' if symbol == args.get(f'g{n}o') else ''}>{symbol}</option>")
            parts.append("""
                </select>
                </fieldset>
                """
            )

        parts.append(f"""
            <fieldset role="group">
                <button data-tooltip="Fewer conditions" class="outline" {hxall.replace("steps", "steps?less=true")} {"disabled" if len(conditions) == 1 else ""}>-</button>
                <button style="width: 100%;" type="submit">Create</button>
                <button data-tooltip="More conditions" class="outline" {hxall.replace("steps", "steps?more=true")} {"disabled" if len(conditions) >= 5 else ""}>+</button>
            </fieldset>
            </div>
        """)
        return "".join(parts)

    def get_extra(self, args):
        payload = args.copy()
        payload.pop("label")
        payload.pop("data_type")
        return json.dumps(payload)

    def detail_for(self, verb):
        import veronique.objects as O
        extra = json.loads(verb.extra)
        parts = [f"""
            <hr>
            <p><span class="svo"><tt class="claim-link">this</tt><span class="inline verb">{verb.label}</span><tt class="claim-link">that</tt></span> if:
            </p>
            <ul>
        """]
        for i in count(start=1):
            if f"g{i}s" not in extra:
                break
            s, v_id, o = extra[f"g{i}s"], extra[f"g{i}v"], extra[f"g{i}o"]
            v = O.Verb(int(v_id))
            parts.append(f"""
                <li><span class="svo"><tt class="claim-link">{s}</tt><span class="inline verb">{v.label}</span><tt class="claim-link">{o}</tt></span></li>
            """)
        parts.append("</ul>")
        return "".join(parts)


class string(DataType):
    can_turn_into = ("text",)
    def display_html(self, value, **_):
        if context.user.redact:
            return '<span class="type-string">"..."</span>'
        return f'<span class="type-string">"{escape(value)}"</span>'

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{escape(value.value)}"'
        else:
            value = ""
        return f"""<input type="text" name="value"{value}></input>"""


class number(DataType):
    def display_html(self, value, **_):
        return f'<span class="type-number">{value}</span>'

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="number" step="any" name="value"{value}></input>"""

    def decode(self, encoded):
        return float_int(encoded)


class color(DataType):
    pattern = re.compile("^#[0-9A-Fa-f]{6}$")

    def display_html(self, value, **_):
        return f"""
            <span style="color: {value}; text-shadow: 0 0 3px black;">&#9632;</span>
            {value}
        """

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{escape(value.value)}"'
        else:
            value = ""
        return f"""<input type="color" name="value"{value}></input>"""

    def extract_value(self, form):
        value = form.get("value")
        if not color.pattern.match(value):
            raise ValueError
        return value


class date(DataType):
    pattern = re.compile("^[0-9?]{4}-[0-9?]{2}-[0-9?]{2}$")

    def display_html(self, value, **_):
        d = NonOmniscientDate(value)
        today = datetime.date.today()
        td = today - d
        if td.days == 0:
            class_ = "date-today"
        elif td.days == 1:
            class_ = "date-yesterday"
        elif td.days == -1:
            class_ = "date-tomorrow"
        else:
            class_ = ""
        return f"""<span class="{class_}">🗓️{value} <em>({td})</em></span>"""

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input
            type="text"
            size=10
            pattern="([0-9?]{4}-[0-9?]{2}-[0-9?]{2}"
            name="value"{value}
        ></input>"""

    def extract_value(self, form):
        value = form.get("value")
        if not date.pattern.match(value):
            raise ValueError
        return value


class boolean(DataType):
    def display_html(self, value, **_):
        if value:
            return """<span style="color: green">✔</span>"""
        else:
            return """<span style="color: red">✘</span>"""

    def input_html(self, value=None, **_):
        checked = " checked" if value and value.value else ""
        return f"""<input type="checkbox" name="value"{checked}></input>"""

    def encode(self, value):
        return value or "off"

    def decode(self, value):
        return value == "on"


class location(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            value = "Point Nemo"
        newline = "\n"
        if COORDS.match(value):
            rand = randint(1, 10000)
            return f"""
                <div id="map{rand}" class="map"></div>
                <script>
                    var map = L.map('map{rand}').setView([{value}], 13);
                    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                        maxZoom: 19,
                        attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    }}).addTo(map);
                    L.marker([{value}]).addTo(map);
                </script>
            """
        else:
            return f"""<span class="type-location">{escape(value).replace(newline, "<br>")} <a
                href="https://www.openstreetmap.org/search?query={
                quote_plus(value.replace(newline, ", "))
            }"
            >🌍</a>"""

    def input_html(self, value=None, **_):
        if value:
            value = value.value
        else:
            value = ""
        rand = randint(1, 10000)
        if COORDS.match(value):
            map_coords = value
        else:
            map_coords = "0, 0"
        return f"""
            <textarea name="value" id="input{rand}">{value}</textarea>
            <div id="map{rand}" class="map"></div>
            <script>
                var map = L.map('map{rand}').setView([{map_coords}], 13);
                L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    maxZoom: 19,
                    attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                }}).addTo(map);
                var marker = null;
                function onMapClick(e) {{
                    document.getElementById("input{rand}").value = e.latlng.lat + "," + e.latlng.lng;
                    if (marker) {{
                      marker.remove()
                    }}
                    marker = L.marker([e.latlng.lat, e.latlng.lng]).addTo(map);
                }}
                map.on('click', onMapClick);
            </script>
        """


class text(DataType):
    can_turn_into = ("string",)
    def __init__(self):
        self.md = MarkdownIt("gfm-like")

    def _sub(self, match):
        import veronique.objects as O
        return f"{O.Claim(int(match.group(1))):link}"

    def display_html(self, value, **_):
        if context.user.redact:
            value = "..."
        else:
            value = self.md.render(escape(value))
        return f"""<span class="type-text">{re.sub(TEXT_REF, self._sub, value)}</span>"""

    def input_html(self, value=None, **_):
        if value:
            value = value.value
        else:
            value = ""
        return f"""
            <textarea name="value">{escape(value)}</textarea>
        """


class email(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            return '<span class="type-email"><a href="mailto:mail@example.com">mail@example.com</a></span>'
        return f'<span class="type-email"><a href="mailto:{escape(value)}">{escape(value)}</a></span>'

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{escape(value.value)}"'
        else:
            value = ""
        return f"""<input type="email" name="value"{value}></input>"""


class website(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            value = "https://example.com"
        return f'<span class="type-website"><a href="{escape(value)}">{escape(value)}</a></span>'

    def input_html(self, value=None, **_):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="url" name="value"{value}></input>"""


class phonenumber(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            value = "+49 1234 56789"
        # no region: values from database should be normalized:
        pn = phonenumbers.parse(value)
        regions = phonenumbers.COUNTRY_CODE_TO_REGION_CODE.get(pn.country_code)
        if regions and len(regions) == 1:
            flag = "".join(
                unicodedata.lookup(f"REGIONAL INDICATOR SYMBOL LETTER {c}")
                for c in regions[0]
            )
        else:
            flag = ""
        display = phonenumbers.format_number(
            pn,
            phonenumbers.PhoneNumberFormat.INTERNATIONAL,
        )
        return f"""<span
            class="type-phonenumber"
        >
            {flag}<a href="tel:{value}">{display}</a>
        </span>"""

    def input_html(self, value=None, **_):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="tel" name="value"{value}></input>"""

    def encode(self, value):
        pn = phonenumbers.parse(value, region=S.default_phone_prefix)
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)


class picture(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            return ""
        return f'<img class="type-picture" src="{value}">'

    def input_html(self, value=None, **_):
        return """<input name="value" type="file"></input>"""


class social(DataType):
    def display_html(self, value, prop, **_):
        if context.user.redact:
            value = "someone"
        return f'<span class="type-social">{prop.extra.format(escape(value))}</span>'

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{escape(value.value)}"'
        else:
            value = ""
        return f"""<input name="value"{value}></input>"""

    def next_step(self, args):
        return """
            <input
                name="template"
                placeholder="template, put {} in there somewhere"
                type="url"
            ></input>
            <button type="submit">»</button>
        """

    def get_extra(self, args):
        return args["template"]


class mtgcolors(DataType):
    def display_html(self, value, **_):
        return "".join(
            f'<span class="mana s{color} small mana-{value[color]}"></span>'
            for color in "wubrg"
            if value.get(color) not in (None, 0, "0")
        )

    def extract_value(self, form):
        return {
            color: int(form.get(f"mana-{color}"))
            for color in "wubrg"
            if int(form.get(f"mana-{color}")) != 0
        }

    def input_html(self, value=None, **_):
        if value:
            value = value.value
        else:
            value = {color: 0 for color in "wubrg"}
        return "".join(
            f"""
            <label><span class="mana s{color} medium"></span>
                <input type="range" name="mana-{color}" min="0" max="5" value="{value[color]}">
            </label>
            """
            for color in "wubrg"
        )

    def decode(self, encoded):
        return json.loads(encoded)

    def encode(self, value):
        return json.dumps(value)


class alpha2(DataType):
    def display_html(self, value, **_):
        country = value.upper()
        flag = "".join(
            unicodedata.lookup(f"REGIONAL INDICATOR SYMBOL LETTER {c}") for c in country
        )
        return f'<span class="type-alpha2">{flag} {country}</span>'

    def encode(self, string):
        val = string.upper()
        if len(val) == 2 and 65 <= ord(val[0]) <= 90 and 65 <= ord(val[1]) <= 90:
            return val
        raise ValueError("Needs to be two-letter ASCII")

    def input_html(self, value=None, **_):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input name="value"{value}></input>"""


class age(DataType):
    def display_html(self, value, **_):
        earliest, latest = value
        if earliest == latest:
            date_range = earliest
        else:
            date_range = f"{earliest}–{latest}"
        return f"{self.possible_ages(value)} years old <small>({date_range})</small>"

    def encode(self, value):
        return "--".join(dt.isoformat() for dt in value)

    def decode(self, encoded):
        if encoded:
            earliest, latest = encoded.split("--")
            return dt_date.fromisoformat(earliest), dt_date.fromisoformat(latest)

    def extract_value(self, form):
        # value can be a plain number, or a range of numbers separated by dash,
        # optionally all prefixed by a date (defaulting to "today"
        value = form.get("value")
        reference_date, _, value = value.rpartition(":")
        if reference_date:
            reference_date = dt_date.fromisoformat(reference_date)
        else:
            reference_date = dt_date.today()
        min_age, _, max_age = value.partition("-")
        if not max_age:
            max_age = min_age

        latest = [reference_date.replace(year=reference_date.year - int(min_age))]
        tomorrow = reference_date + timedelta(days=1)
        earliest = [tomorrow.replace(year=tomorrow.year - (int(max_age) + 1))]

        if "previous" in form:
            prev_earliest, prev_latest = form.get("previous").split("--")
            latest.append(dt_date.fromisoformat(prev_latest))
            earliest.append(dt_date.fromisoformat(prev_earliest))

        return max(earliest), min(latest)

    @staticmethod
    def age_from_date(dt):
        today = dt_date.today()
        return today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))

    @staticmethod
    def possible_ages(dates):
        return "-".join(
            sorted({str(a) for a in (age.age_from_date(dt) for dt in dates)})
        )

    def input_html(self, value=None, **_):
        if value:
            # value is now a tuple of earliest and latest possible date
            earliest, latest = value.value
            return f"""
            <input name="value" value="{self.possible_ages(value.value)}"></input>
            <input type="hidden" name="previous" value="{earliest:%Y-%m-%d}--{latest:%Y-%m-%d}">
            """
        else:
            return '<input name="value">'


class choice(DataType):
    def display_html(self, value, **_):
        return f'<span class="type-choice">{escape(value)}</span>'

    def next_step(self, args):
        return """
            <label>Enter possible choices. One choice per line.
            <textarea name="choices"></textarea>
            </label>
            <button type="submit">Create</button>
        """

    def get_extra(self, args):
        return json.dumps([choice for choice in args["choices"].split("\n") if choice])

    def detail_for(self, verb):
        choices = json.loads(verb.extra)
        return f"""
            <h4>Choices:</h4>
            <ul>
                {"".join(f"<li>{choice}</li>" for choice in choices)}
            </ul>
        """

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        choices = json.loads(O.Verb(verb_id).extra)
        return f"""
            <select name="value">
                {"".join(f'<option name="{choice}" {"selected" if choice == value else ""}>{choice}</option>' for choice in choices)}
            </select>
        """

    @property
    def compatible_types(self):
        # choice and choices can't be reverbed (not even to verbs of the same
        # data type), because other verbs will have different choices
        return ()

class choices(choice):
    def display_html(self, value, **_):
        return ", ".join(f'<span class="type-choice">{escape(choice)}</span>' for choice in value)

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        choices = json.loads(O.Verb(verb_id).extra)
        return f"""
            <select name="value" multiple>
                {"".join(f'<option name="{choice}" {"selected" if value and choice in value.value else ""}>{choice}</option>' for choice in choices)}
            </select>
        """

    def extract_value(self, form):
        """
        Given a form object, extract the value in the form we want it.

        Typically, this is just whatever is in the value field, but this can be
        used to implement widgets with several <input>s.
        """
        return form["value"]

    def encode(self, value):
        """Encode how value should be represented in the DB."""
        return json.dumps(value)

    def decode(self, encoded):
        """Decode from string in database to desired value."""
        return json.loads(encoded)
