import base64
import datetime
import json
import os
import re
import unicodedata
from datetime import date as dt_date
from datetime import timedelta
from functools import partial
from html import escape
from itertools import count
from pathlib import Path
from random import randint
from urllib.parse import quote_plus
from uuid import uuid4

import phonenumbers
import pycountry
from markdown_it import MarkdownIt
from nh3 import clean as clean_html

from veronique.autocomplete import AUTOCOMPLETES
from veronique.context import context
from veronique.nomnidate import NonOmniscientDate
from veronique.settings import settings as S
from veronique.utils import D, fragment

TYPES = {}
TEXT_REF = re.compile(r"\[@(\d+)\]")
INPUT_WIDGET_REF = re.compile(r'<span [^>]+data-claim-ref="(\d+)"[^>]+>.+?</span>')
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

    def edit_verb(self, verb, form):
        return ""

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
    def input_html(self, value=None, claim_ids=None, direction=None, verb_id=None, allow_connect=True, **_):
        return AUTOCOMPLETES["link"].widget(
            data=f"{claim_ids}:{direction}:{verb_id}" if allow_connect else None
        )


class undirected_link(directed_link):
    pass


class inferred(DataType):
    def next_step(self, args):
        import veronique.objects as O
        hxall = 'hx-select="#autoform" hx-swap="outerMorph" hx-target="#autoform" hx-get="/verbs/new/steps" hx-include="closest form"'
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
    can_turn_into = ("text", "source")
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


class source(string):
    can_turn_into = ("string", "text")

    def display_html(self, value, **_):
        import veronique.objects as O
        if context.user.redact:
            return '<span class="type-source">"..."</span>'
        variant, value = value[0], value[1:]
        if variant == "T":
            return f'<span class="type-source type-source-text">"{escape(value)}"</span>'
        if variant == "U":
            return f'<span class="type-source type-source-url"><a href="{escape(value)}">{escape(value)}</a></span>'
        if variant == "E":
            entity = O.Claim(int(value))
            return f'<span class="type-source type-source-entity">{entity}</span>'

    def _input_for_variant(self, variant, value):
        if variant == "T":
            if value:
                return f"""<input type="text" name="value" value="{escape(value)}">"""
            return """<input type="text" name="value">"""
        elif variant == "U":
            if value:
                return f"""<input type="url" name="value" value="{escape(value)}">"""
            return """<input type="url" name="value">"""
        elif variant == "E":
            return AUTOCOMPLETES["link"].widget(None)

    def extract_value(self, form):
        """
        Given a form object, extract the value in the form we want it.

        Typically, this is just whatever is in the value field, but this can be
        used to implement widgets with several <input>s.
        """
        value = form.get("value")
        variant = form.get("variant")
        assert variant in ("T", "U", "E")
        return f"{variant}{value}"

    def input_html(self, value=None, **_):
        if value:
            variant, value = value.value[0], value.value[1:]
        else:
            variant = S.default_source_type

        input = self._input_for_variant(variant, value)
        return f"""
        <fieldset hx-trigger="change" hx-get="/verbs/data-types/source" hx-target="#source-value-container" hx-include="this">
            <legend>Type of source:</legend>
            <label>
                <input type="radio" name="variant" value="T" {"checked" if variant == "T" else ""}>
                Text
            </label>
            <label>
                <input type="radio" name="variant" value="U" {"checked" if variant == "U" else ""}>
                Website
            </label>
            <label>
                <input type="radio" name="variant" value="E" {"checked" if variant == "E" else ""}>
                Entity
            </label>
        </fieldset>
        <div id="source-value-container">
            {input}
        </div>
        """
        return f"""<input type="text" name="value"{value}></input>"""

    @fragment
    async def request(self, request, *, method):
        if method == "GET":
            return self._input_for_variant(D(request.args)["variant"], value=None)
        return "@"


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
    def display_html(self, value, prop, **_):
        d = NonOmniscientDate(value, negating_days_allowed="a" not in (prop.extra or ""))
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
        astro = ""
        if "s" in (prop.extra or "") and "?" not in value[-5:]:
            # we have day and month and want zodiac signs
            if (astronum := int(value[-5:].replace("-", ""))) < 120 or astronum > 1221:
                astro = '<span data-tooltip="Capricorn">♑︎</span>'
            elif astronum < 219:
                astro = '<span data-tooltip="Aquarius">♒︎</span>'
            elif astronum < 321:
                astro = '<span data-tooltip="Pisces">♓︎</span>'
            elif astronum < 420:
                astro = '<span data-tooltip="Aries">♈︎</span>'
            elif astronum < 521:
                astro = '<span data-tooltip="Taurus">♉︎</span>'
            elif astronum < 622:
                astro = '<span data-tooltip="Gemini">♊︎</span>'
            elif astronum < 723:
                astro = '<span data-tooltip="Cancer">♋︎</span>'
            elif astronum < 823:
                astro = '<span data-tooltip="Leo">♌︎</span>'
            elif astronum < 923:
                astro = '<span data-tooltip="Virgo">♍︎</span>'
            elif astronum < 1024:
                astro = '<span data-tooltip="Libra">♎︎</span>'
            elif astronum < 1122:
                astro = '<span data-tooltip="Scorpio">♏︎</span>'
            elif astronum < 1222:
                astro = '<span data-tooltip="Sagittarius">♐︎</span>'
            else:
                raise RuntimeError("Unexpected date")
        fmt_flags = "a" if "a" in (prop.extra or "") else ""
        if value == "????-??-??":
            value = "unknown"
        else:
            value = value.removeprefix("????-").removesuffix("-??-??")
        return f"""<span class="{class_}">🗓️{value}{astro} <em>({td:{fmt_flags}})</em></span>"""

    def extract_value(self, form):
        value = form.get("value")
        if value in ("today", "yesterday", "tomorrow"):
            t = dt_date.today()
            return {
                "yesterday": str(t - timedelta(days=1)),
                "today": str(t),
                "tomorrow": str(t + timedelta(days=1)),
            }[value]
        return value

    def input_html(self, value=None, **_):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input
            type="text"
            size=10
            pattern="[0-9?]{{4}}-[0-9?]{{2}}-[0-9?]{{2}}|[0-9?]{{4}}|[0-9?]{{2}}-[0-9?]{{2}}|[?]|today|yesterday|tomorrow"
            name="value"{value}
        ><small>Possible formats: <tt>YYYY-mm-dd</tt>, <tt>YYYY</tt>, <tt>mm-dd</tt>, <tt>?</tt>. Any digit can also be replaced by a question mark. You may also use any of these short hands: <tt>yesterday</tt>, <tt>today</tt>, <tt>tomorrow</tt></small>.
        """

    def get_extra(self, args):
        return "".join(
            name[0] for name in ("starsign", "age") if name in args
        )

    def edit_verb_form(self, verb):
        flags = verb.extra or ""
        return f"""
            <fieldset>
            <legend>Options</legend>
            <label>
              <input type="checkbox" name="starsign" {"checked" if "s" in flags else ""} />
              Show star sign when possible
            </label>
            <label>
              <input type="checkbox" name="age" {"checked" if "a" in flags else ""} />
              Show as age
            </label>
              <small>Will always show correct age when possible, never e.g. "5 years ago, in 3 days".</small>
            </fieldset>
        """

    def edit_verb(self, verb, form):
        new_extra = self.get_extra(form)
        verb.extra = new_extra


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
                    L.tileLayer('{S.map_tile_url}', {{
                        maxZoom: 19,
                        attribution: '&copy; <a href="{S.map_tile_attribution_link}">{S.map_tile_attribution_label}</a>'
                    }}).addTo(map);
                    L.marker([{value}]).addTo(map);
                </script>
            """
        else:
            return f"""<span class="type-location">{escape(value).replace(newline, "<br>")} <a
                href="{S.location_link_template.format(
                quote_plus(value.replace(newline, ", "))
                )}"
            >🌍</a></span>"""

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
                L.tileLayer('{S.map_tile_url}', {{
                    maxZoom: 19,
                    attribution: '&copy; <a href="{S.map_tile_attribution_link}">{S.map_tile_attribution_label}</a>'
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
    can_turn_into = ("string", "source")
    def __init__(self):
        self.md = MarkdownIt("gfm-like")

    def _sub(self, match, fmt=None):
        import veronique.objects as O
        if fmt:
            return f"{O.Claim(int(match.group(1))):{fmt}}"
        else:
            return f"{O.Claim(int(match.group(1)))}"

    def display_html(self, value, fmt=None, **_):
        if len(value) > 100 and fmt == "nested":
            value = f"{value[:100]}[...]"
        if context.user.redact:
            value = "..."
        else:
            value = self.md.render(value)
        return f"""<span class="type-text">{re.sub(TEXT_REF, self._sub, value)}</span>"""

    def _encode_input_widget_refs(self, match):
        return f'[@{match.group(1)}]'

    def extract_value(self, form):
        return re.sub(INPUT_WIDGET_REF, self._encode_input_widget_refs, form.get("value")).strip()

    def encode(self, value):
        # This removes "dangerous" HTML (scripts, meta tags, <link>, etc.)
        return clean_html(value).replace("<div>", "").replace("</div>", "\n\n")

    def input_html(self, value=None, **_):
        if value:
            value = value.value
        else:
            value = ""
        value = value.strip()
        value = re.sub(TEXT_REF, partial(self._sub, fmt="input-widget-ref"), value)
        if value.endswith(">"):
            value = f"{value}&nbsp;"
        return f"""
            <div
                class="input-text"
                onkeyup="document.getElementsByName('value')[0].innerHTML = this.innerHTML"
                onchange="document.getElementsByName('value')[0].innerHTML = this.innerHTML"
                hx-on:keydown="if(event.key==='@'){{ event.preventDefault(); htmx.trigger(this, 'at-key'); }}"
                hx-trigger="at-key"
                hx-post="/verbs/data-types/text"
                hx-swap="beforeend"
                contenteditable>{value}</div>
            <textarea style="display: none;" name="value">{value}</textarea>
        """

    @fragment
    async def request(self, request, *, method):
        if method == "POST":
            return AUTOCOMPLETES["input_ref_widget"].widget(None)
        return "@"


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
        if regions:
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
            {flag} <a href="tel:{value}">{display}</a>
        </span>"""

    def input_html(self, value=None, **_):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""
            <input type="tel" name="value"{value}>
            <small>Non-international phone numbers (without the <tt>+</tt> prefix) will be interpreted as being from region {S.default_phone_region}.</small>
        """

    def encode(self, value):
        pn = phonenumbers.parse(value, region=S.default_phone_region)
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)


class picture(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            return ""
        return f'<img class="type-picture" src="{value}">'

    def extract_value(self, form):
        f = form["value"]
        return f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"

    def input_html(self, value=None, **_):
        return """<input name="value" type="file"></input>"""


class file(DataType):
    FILE_PATH = Path(os.environ.get("VERONIQUE_USER_CONTENT_PATH", "user-content"))
    EMBED_MIME_TYPES = (
        "image/jpeg",
        "image/png",
    )

    def display_html(self, value, **_):
        if context.user.redact:
            return ""
        mime, filename, ref = value.split(":")
        if mime in file.EMBED_MIME_TYPES:
            return f'<img class="type-file" src="/user-content/{ref}/{filename}">'
        else:
            return f'<span class="type-file"><a href="/user-content/{ref}/{filename}">\N{PAPERCLIP} {filename}</a></span>'

    # TODO: figure out how to delete files. Perhaps just via "GC" by finding
    # files with no references to them.

    def extract_value(self, form):
        f = form["value"]
        identifier = str(uuid4())
        with (file.FILE_PATH / identifier).open("wb") as out:
            out.write(f.body)
        filename = self._sanitize(f.name)
        return f"{f.type}:{filename}:{identifier}"

    def _sanitize(self, name):
        return "".join(
            c
            for c in name
            if (
                unicodedata.category(c).startswith("L")
                or c in " 1234567890-."
            )
        ).replace(" ", "_")

    def input_html(self, value=None, **_):
        return """<input name="value" type="file"></input>"""


class social(DataType):
    def display_html(self, value, prop, **_):
        if context.user.redact:
            value = "someone"
        user = escape(value)
        value = prop.extra.format(user)
        if value.startswith("http"):
            value = f'<a href="{value}">{user}</a>'
        return f'<span class="type-social">{value}</span>'

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        if value:
            value = f' value="{escape(value.value)}"'
        else:
            value = ""
        before, _, after  = O.Verb(verb_id).extra.partition("{}")
        parts = ['<fieldset role="group">']
        if before:
            parts.append(f'<input value="{before}" disabled>')
        parts.append(f'<input name="value"{value}>')
        if after:
            parts.append(f'<input value="{after}" disabled>')
        parts.append("</fieldset>")
        return "".join(parts)

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
                <input type="range" name="mana-{color}" min="0" max="5" value="{value.get(color, 0)}">
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
        try:
            country = pycountry.countries.lookup(value.upper())
        except LookupError:
            return f'<span class="type-alpha2">invalid country ({value.upper()})</span>'
        return f'<span class="type-alpha2">{country.flag} {country.name}</span>'

    def encode(self, string):
        val = string.upper()
        if len(val) == 2 and 65 <= ord(val[0]) <= 90 and 65 <= ord(val[1]) <= 90:
            return val
        raise ValueError("Needs to be two-letter ASCII")

    def input_html(self, value=None, **_):
        if value:
            if not isinstance(value, str):
                value = value.value
            quot = '"'
            value = f' value="{value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""
            <div class="ac-widget">
            <input hx-trigger="keyup" hx-get="/verbs/data-types/alpha2" hx-target="#alpha2-results" name="value"{value} autocomplete="off">
            <small>Enter a two-uppercase-letter region code here (ISO 3166-1 alpha 2), e.g. "DE".</small>
            <div id="alpha2-results" class="ac-results"></div>
            </div>
        """

    @fragment
    async def request(self, request, *, method):
        args = D(request.args)
        if "accept" in args:
            return self.input_html(value=args["accept"])
        if "value" not in args:
            return ""
        value = args["value"]

        try:
            results = pycountry.countries.search_fuzzy(value)
        except LookupError:
            results = []
        return "".join(f'''<a
            class="clickable ac-result"
            hx-target="closest .ac-widget"
            hx-swap="outerMorph"
            hx-get="/verbs/data-types/alpha2/?accept={c.alpha_2}"
        >{c.flag} {c.name}</a>
        ''' for c in results[:5])


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
            <input name="value" value="{self.possible_ages(value.value)}">
            <small>Format: <tt>optional-date:age</tt>. The age can also be a range. E.g.: <tt>2026-03-05:42-44</tt>. Updates restrict further.</small>
            <input type="hidden" name="previous" value="{earliest:%Y-%m-%d}--{latest:%Y-%m-%d}">
            """
        else:
            return """
                <input name="value">
                <small>Format: <tt>optional-date:age</tt>. The age can also be a range. E.g.: <tt>2026-03-05:42-44</tt></small>
            """


class daterange(DataType):
    def display_html(self, value, **_):
        earliest, latest = value
        if earliest == latest:
            date_range = str(earliest)
        elif str(earliest).endswith("-01-01") and str(latest).endswith("-12-31"):
            # full years
            if earliest.year == latest.year:
                return str(earliest.year)
            else:
                return f"{earliest.year} – {latest.year}"
        else:
            date_range = f"{earliest} – {latest}"
        # TODO: add nice form for full months as well
        return date_range

    encode = age.encode
    decode = age.decode

    def extract_value(self, form):
        earliest, latest = form.get("value_earliest"), form.get("value_latest")
        if not latest:
            latest = earliest
        return dt_date.fromisoformat(earliest), dt_date.fromisoformat(latest)

    def input_html(self, value=None, **_):
        if value:
            # value is now a tuple of earliest and latest possible date
            earliest, latest = value.value
            if earliest == latest:
                latest = ""
            else:
                latest = f' value="{latest}"'
            earliest = f' value="{earliest}"'
        else:
            earliest = latest = ""

        pattern = r"[0-9?]{4}-[0-9?]{2}-[0-9?]{2}"
        return f"""
            <fieldset role="group">
            <input name="value_earliest" pattern="{pattern}" placeholder="Date, or earliest possible date"{earliest}>
            <input value="–" style="width: 50px;" disabled>
            <input name="value_latest" pattern="{pattern}" placeholder="Latest date (optional)"{latest}>
            </fieldset>
        """


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
        return json.dumps([choice.strip() for choice in args["choices"].split("\n") if choice.strip()])

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

    def edit_verb_form(self, verb):
        choices = [c.strip() for c in json.loads(verb.extra)]
        newline = "\n"
        return f"""
            <label>Enter possible choices. One choice per line.
            <textarea name="choices">{newline.join(choices)}</textarea>
            </label>
        """

    def edit_verb(self, verb, form):
        new_extra = self.get_extra(form)
        new = set(json.loads(new_extra))
        old = set(json.loads(verb.extra))
        if old - new:
            raise ValueError(f"Can't remove values from choice(s): {set(json.loads(new_extra)) - set(verb.extra)} (old: {old}, new: {new})")
        verb.extra = new_extra

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
