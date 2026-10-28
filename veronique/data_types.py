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
from itertools import combinations, count
from pathlib import Path
from random import randint
from types import SimpleNamespace
from urllib.parse import quote_plus
from uuid import uuid4

import phonenumbers
import pycountry
from markdown_it import MarkdownIt
from nh3 import clean as clean_html

from veronique.autocomplete import Tags, widget
from veronique.constants import COORDS, DATE_REF, INPUT_WIDGET_REF, TEXT_REF
from veronique.context import context
from veronique.html import H, join
from veronique.nomnidate import NonOmniscientDate
from veronique.settings import settings as S
from veronique.utils import D, fragment

TYPES = {}


def float_int(val):
    val = float(val)
    if val.is_integer():
        val = int(val)
    return val


class DataType:
    can_turn_into = ()
    supports_value_query = False

    def __init_subclass__(cls):
        TYPES[cls.__name__] = cls()

    def display_html(self, value, **_):
        return H(f"placeholder, not implemented for data type {type(self).__name__}.")

    def input_html(self, value=None, **_):
        return H(f"placeholder, not implemented for data type {type(self).__name__}.")

    def edit_verb(self, verb, form):
        pass

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
        return None

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
        return widget(
            Tags(f"connect={claim_ids}:{direction}:{verb_id}" if allow_connect else ""),
        )


class undirected_link(directed_link):
    pass


class inferred(DataType):
    def next_step(self, args):
        import veronique.objects as O
        hxall = {
            "hx_select": "#autoform",
            "hx_swap": "outerMorph",
            "hx_target": "#autoform",
            "hx_get": "/verbs/new/steps",
            "hx_include": "closest form",
        }
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

        rules = []

        for n, (subj, selected_verb_id, obj) in enumerate(conditions, start=1):
            rules.append(
                H.fieldset(
                    H.select(
                        *(H.option(symbol, selected=symbol==args.get(f"g{n}s")) for symbol in alphabet),
                        name=f"g{n}s",
                        **hxall,
                    ),
                    H.select(
                        *(H.option(verb.label, value=str(verb.id), selected=verb.id==selected_verb_id) for verb in verbs),
                        name=f"g{n}v",
                        **hxall,
                    ),
                    H.select(
                        *(H.option(symbol, selected=symbol==args.get(f"g{n}o")) for symbol in alphabet),
                        name=f"g{n}o",
                        **hxall,
                    ),
                    role="group",
                )
            )

        return H.div(
            H.p(
                "There will be a new relation ",
                H.span(
                    H.tt("this", cls="claim-link"),
                    H.span(label, cls="inline verb"),
                    H.tt("that", cls="claim-link"),
                    cls="svo",
                ),
                " if:",
                *rules,
                H.fieldset(
                    H.button(
                        "-",
                        data_tooltip="Fewer conditions",
                        cls="outline",
                        **(hxall | {"hx_get": "/verbs/new/steps?less=true"}),
                        disabled=len(conditions)==1,
                    ),
                    H.button("Create", type="submit", style="width: 100%;"),
                    H.button(
                        "+",
                        data_tooltip="More conditions",
                        cls="outline",
                        **(hxall | {"hx_get": "/verbs/new/steps?more=true"}),
                        disabled=len(conditions)>=5,
                    ),
                    role="group",
                )
            ),
            id="autoform",
        )

    def get_extra(self, args):
        payload = args.copy()
        payload.pop("label")
        payload.pop("data_type")
        # Determine connectedness:
        buckets = set()
        for k, v in payload.items():
            if k.endswith("v"):
                continue
            n = k.strip("gos")
            buckets.add(frozenset({n, v}))
        for i in range(len(buckets)):
            for a, b in combinations(buckets, 2):
                if a & b:
                    buckets.remove(a)
                    buckets.remove(b)
                    buckets.add(frozenset({*a, *b}))
                    break
        if len(buckets) != 1:
            raise ValueError("Inferred verb isn't fully connected")
        if {"this", "that"} - buckets.pop():
            raise ValueError("Inferred verb needs to have this and that.")
        return json.dumps(payload)

    def detail_for(self, verb):
        import veronique.objects as O
        extra = json.loads(verb.extra)
        parts = []
        for i in count(start=1):
            if f"g{i}s" not in extra:
                break
            s, v_id, o = extra[f"g{i}s"], extra[f"g{i}v"], extra[f"g{i}o"]
            v = O.Verb(int(v_id))
            parts.append(
                H.li(
                    H.span(
                        H.tt(
                            s,
                            cls="claim-link",
                        ),
                        H.span(
                            v.label,
                            cls="inline verb",
                        ),
                        H.tt(
                            o,
                            cls="claim-link",
                        ),
                        cls="svo",
                    )
                )
            )
        return H(
            H.hr(),
            H.p(
                H.span(
                    H.tt("this", cls="claim-link"),
                    H.span(verb.label, cls="inline verb"),
                    H.tt("that", cls="claim-link"),
                    cls="svo",
                ),
                " if:",
            ),
            H.ul(*parts),
        )


class string(DataType):
    can_turn_into = ("text", "source")
    def display_html(self, value, **_):
        if context.user.redact:
            return H.span('"..."', cls="type-string")
        return H.span(escape(value), cls="type-string")

    def input_html(self, value=None, **_):
        if value:
            value = {"value": escape(value.value)}
        else:
            value = {}
        return H.input(type="text", name="value", **value)


class source(string):
    can_turn_into = ("string", "text")

    def display_html(self, value, **_):
        import veronique.objects as O
        if context.user.redact:
            return H.span('"..."', cls="type-source")
        variant, value = value[0], value[1:]
        if variant == "T":
            return H.span(
                f'"{escape(value)}"',
                cls="type-source type-source-text",
            )
        if variant == "U":
            return H.span(
                H.a(escape(value), href=escape(value)),
                cls="type-source type-source-url",
            )
        if variant == "E":
            entity = O.Claim(int(value))
            return H.span(entity.html(), cls="type-source type-source-entity")

    def _input_for_variant(self, variant, value):
        if variant == "T":
            if value:
                return H.input(type="text", name="value", value=escape(value))
            return H.input(type="text", name="value")
        elif variant == "U":
            if value:
                return H.input(type="url", name="value", value=escape(value))
            return H.input(type="url", name="value")
        elif variant == "E":
            return widget(Tags(""))

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
        return H(
            H.fieldset(
                H.legend("Type of source:"),
                H.label(
                    H.input(type="radio", name="variant", value="T", checked=variant=="T"),
                    "Text",
                ),
                H.label(
                    H.input(type="radio", name="variant", value="U", checked=variant=="U"),
                    "Website",
                ),
                H.label(
                    H.input(type="radio", name="variant", value="E", checked=variant=="E"),
                    "Entity",
                ),
                hx_trigger="change",
                hx_get="/types/source",
                hx_target="#source-value-container",
                hx_include="this",
            ),
            H.div(
                input,
                id="source-value-container",
            ),
        )

    @fragment
    async def request(self, request, *, method):
        if method == "GET":
            return self._input_for_variant(D(request.args)["variant"], value=None)
        return H("@")


class number(DataType):
    def display_html(self, value, **_):
        return H.span(str(value), cls="type-number")

    def input_html(self, value=None, **_):
        if value:
            value = {"value": str(value.value)}
        else:
            value = {}
        return H.input(type="number", step="any", name="value", **value)

    def decode(self, encoded):
        return float_int(encoded)


class color(DataType):
    pattern = re.compile("^#[0-9A-Fa-f]{6}$")
    supports_value_query = True

    def display_html(self, value, **_):
        return H(
            H.span("&#9632;", style=f"color: {value}; text-shadow: 0 0 3px black;"),
            value,
        )

    def input_html(self, value=None, **_):
        if value:
            value = {"value": escape(value.value)}
        else:
            value = {}
        return H.input(type="color", name="value", **value)

    def extract_value(self, form):
        value = form.get("value")
        if not color.pattern.match(value):
            raise ValueError
        return value


class date(DataType):
    supports_value_query = True

    def display_html(self, value, prop=None, **_):
        if prop is None:
            prop = SimpleNamespace(extra="")
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
                astro = H.span(
                    "♑︎",
                    data_tooltip="Capricorn",
                )
            elif astronum < 219:
                astro = H.span(
                    "♒︎",
                    data_tooltip="Aquarius",
                )
            elif astronum < 321:
                astro = H.span(
                    "♓︎",
                    data_tooltip="Pisces",
                )
            elif astronum < 420:
                astro = H.span(
                    "♈︎",
                    data_tooltip="Aries",
                )
            elif astronum < 521:
                astro = H.span(
                    "♉︎",
                    data_tooltip="Taurus",
                )
            elif astronum < 622:
                astro = H.span(
                    "♊︎",
                    data_tooltip="Gemini",
                )
            elif astronum < 723:
                astro = H.span(
                    "♋︎",
                    data_tooltip="Cancer",
                )
            elif astronum < 823:
                astro = H.span(
                    "♌︎",
                    data_tooltip="Leo",
                )
            elif astronum < 923:
                astro = H.span(
                    "♍︎",
                    data_tooltip="Virgo",
                )
            elif astronum < 1024:
                astro = H.span(
                    "♎︎",
                    data_tooltip="Libra",
                )
            elif astronum < 1122:
                astro = H.span(
                    "♏︎",
                    data_tooltip="Scorpio",
                )
            elif astronum < 1222:
                astro = H.span(
                    "♐︎",
                    data_tooltip="Sagittarius",
                )
            else:
                raise RuntimeError("Unexpected date")
        fmt_flags = "a" if "a" in (prop.extra or "") else ""
        if value == "????-??-??":
            value = "unknown"
        else:
            value = value.removeprefix("????-").removesuffix("-??-??")
        return H.span(
            "🗓️",
            H.a(
                value,
                href=f'/types/date/{value.replace("?", "%3F")}',
            ),
            astro,
            " ",
            H.em(f"({td:{fmt_flags}})"),
            cls=f"type-date {class_}",
        )

    def extract_value(self, form):
        value = form.get("value")
        if value in ("today", "yesterday", "tomorrow"):
            t = dt_date.today()
            value = {
                "yesterday": str(t - timedelta(days=1)),
                "today": str(t),
                "tomorrow": str(t + timedelta(days=1)),
            }[value]
        return str(NonOmniscientDate(value))

    def input_html(self, value=None, **_):
        if value:
            value = {"value": str(value.value)}
        else:
            value = {}
        return H(
            H.input(
                type="text",
                size="10",
                pattern="[0-9?]{4}-[0-9?]{2}-[0-9?]{2}|[0-9?]{4}|[0-9?]{2}-[0-9?]{2}|[?]|today|yesterday|tomorrow",
                name="value",
                **value,
            ),
            H.small(
                "Possible formats: ",
                H.tt("YYYY-mm-dd"),
                ", ",
                H.tt("YYYY"),
                ", ",
                H.tt("mm-dd"),
                ", ",
                H.tt("?"),
                ". Any digit can also be replaced by a question mark. You may also use any of these short hands: ",
                H.tt("yesterday"),
                ", ",
                H.tt("today"),
                ", ",
                H.tt("tomorrow"),
            ),
        )


    def get_extra(self, args):
        return "".join(
            name[0] for name in ("starsign", "age") if name in args
        )

    def edit_verb_form(self, verb):
        flags = verb.extra or ""
        return H.fieldset(
            H.legend("Options"),
            H.label(
                H.input(type="checkbox", name="starsign", checked="s" in flags),
                "Show star sign when possible",
            ),
            H.label(
                H.input(type="checkbox", name="age", checked="a" in flags),
                "Show as age",
            ),
            H.small('Will always show correct age when possible, never e.g. "5 years ago, in 3 days".'),
        )

    def edit_verb(self, verb, form):
        new_extra = self.get_extra(form)
        verb.extra = new_extra

    def value_query_extra(self, value):
        if "?" in value:
            return ""
        return f"(a {dt_date.fromisoformat(value):%A})"


class boolean(DataType):
    def display_html(self, value, **_):
        if value:
            return H.span("✔", style="color: green;")
        else:
            return H.span("✘", style="color: red;")

    def input_html(self, value=None, **_):
        return H.input(type="checkbox", name="value", checked=value and value.value)

    def encode(self, value):
        return value or "off"

    def decode(self, value):
        return value == "on"


class location(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            value = "Point Nemo"
        if COORDS.match(value):
            rand = randint(1, 10000)
            return H(
                H.div("", id=f"map{rand}", cls="map type-location"),
                H.script(f"""
                    var map = L.map('map{rand}').setView([{value}], 13);
                    L.tileLayer('{S.map_tile_url}', {{
                        maxZoom: 19,
                        attribution: '&copy; <a href="{S.map_tile_attribution_link}">{S.map_tile_attribution_label}</a>',
                        referrerPolicy: 'origin',
                    }}).addTo(map);
                    L.marker([{value}]).addTo(map);
                """),
            )
        else:
            return H.span(
                *join(H.br(), escape(value).split("\n")),
                " ",
                H.a("🌍", href=S.location_link_template.format(quote_plus(value.replace("\n", ", ")))),
                cls="type-location",
            )

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
        return H(
            H.textarea(
                value,
                name="value",
                id=f"input{rand}",
            ),
            H.div("", id=f"map{rand}", cls="map type-location"),
            H.script(f"""
                var map = L.map('map{rand}').setView([{map_coords}], 13);
                L.tileLayer('{S.map_tile_url}', {{
                    maxZoom: 19,
                    attribution: '&copy; <a href="{S.map_tile_attribution_link}">{S.map_tile_attribution_label}</a>',
                    referrerPolicy: 'origin',
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
            """),
        )


class text(DataType):
    can_turn_into = ("string", "source")
    def __init__(self):
        self.md = MarkdownIt("gfm-like")

    def _sub(self, match, fmt=None):
        import veronique.objects as O
        if fmt == "input-widget-ref":
            return str(O.Claim(int(match.group(1))).html(fmt))
        elif fmt == "date":
            value = match.group(0)
            return f"""<span class="type-date">🗓️<a href="/types/date/{value}">{value}</a></span>"""
        else:
            return f"{O.Claim(int(match.group(1)))}"

    def display_html(self, value, fmt=None, **_):
        if len(value) > 100 and fmt == "nested":
            value = f"{value[:100]}[...]"
        if context.user.redact:
            value = "..."
        else:
            value = self.md.render(value)
        # TODO: more reference types
        value = re.sub(TEXT_REF, self._sub, value)
        value = re.sub(DATE_REF, partial(self._sub, fmt="date"), value)
        return H.span(
            value,
            cls="type-text",
        )

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
        return H(
            H.div(
                value,
                cls="input-text",
                onkeyup="document.getElementsByName('value')[0].innerHTML = this.innerHTML",
                onchange="document.getElementsByName('value')[0].innerHTML = this.innerHTML",
                hx_on__keydown="if(event.key==='@'){{ event.preventDefault(); htmx.trigger(this, 'at-key'); }}",
                hx_trigger="at-key",
                hx_post="/types/text",
                hx_swap="beforeend",
                contenteditable=True,
            ),
            H.textarea(
                value,
                style="display: none;",
                name="value",
            ),
        )

    @fragment
    async def request(self, request, *, method):
        if method == "POST":
            return widget(Tags("ir"))


class email(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            return H.span(
                H.a(
                    "mail@example.com",
                    href="mailto:mail@example.com",
                ),
                cls="type-email",
            )
        return H.span(
            H.a(
                escape(value),
                href=f"mailto:{escape(value)}",
            ),
            cls="type-email",
        )

    def input_html(self, value=None, **_):
        if value:
            value = escape(value.value)
        else:
            value = {}
        return H.input(type="email", name="value", **value)


class website(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            value = "https://example.com"
        return H.span(
            H.a(
                escape(value),
                href=escape(value),
            ),
            cls="type-website",
        )

    def input_html(self, value=None, **_):
        if value:
            value = {"value": value.value.replace('"', "&quot;")}
        else:
            value = {}
        return H.input(type="url", name="value", **value)


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
        return H.span(
            flag,
            " ",
            H.a(display, href=f"tel:{value}"),
            cls="type-phonenumber",
        )

    def input_html(self, value=None, **_):
        if value:
            value = {"value": value.value.replace('"', "&quot;")}
        else:
            value = {}
        return H(
            H.input(type="tel", name="value", **value),
            H.small(
                "Non-international phone numbers (without the ",
                H.tt("+"),
                f" prefix) will be interpreted as being from region {S.default_phone_region}.",
            ),
        )

    def encode(self, value):
        pn = phonenumbers.parse(value, region=S.default_phone_region)
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)


class picture(DataType):
    def display_html(self, value, **_):
        if context.user.redact:
            return None
        return H.img(cls="type-picture", src=value)

    def extract_value(self, form):
        f = form["value"]
        return f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"

    def input_html(self, value=None, **_):
        return H.input(name="value", type="file")


class file(DataType):
    FILE_PATH = Path(os.environ.get("VERONIQUE_USER_CONTENT_PATH", "user-content"))
    EMBED_MIME_TYPES = (
        "image/jpeg",
        "image/png",
    )

    def display_html(self, value, **_):
        if context.user.redact:
            return None
        mime, filename, ref = value.split(":")
        if mime in file.EMBED_MIME_TYPES:
            return H.img(
                cls="type-file",
                src=f"/user-content/{ref}/{filename}",
            )
        else:
            return H.span(
                H.a(f"\N{PAPERCLIP} {filename}", href=f"/user-content/{ref}/{filename}"),
                cls="type-file",
            )

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
        return H.input(name="value", type="file")


class social(DataType):
    def display_html(self, value, prop=None, **_):
        if context.user.redact:
            value = "someone"
        user = escape(value)
        if prop is not None:
            value = prop.extra.format(user)
        else:
            value = user
        if value.startswith("http"):
            value = H.a(user, href=value)
        return H.span(value, cls="type-social")

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        if value:
            value = {"value": escape(value.value)}
        else:
            value = {}
        before, _, after  = O.Verb(verb_id).extra.partition("{}")
        return H.fieldset(
            H.input(value=before, disabled=True) if before else None,
            H.input(name="value", **value),
            H.input(value=after, disabled=True) if after else None,
            role="group",
        )

    def next_step(self, args):
        return H(
            H.input(name="template", placeholder="template, put {} in there somewhere", type="url"),
            H.button("»", type="submit"),
        )

    def get_extra(self, args):
        return args["template"]


class mtgcolors(DataType):
    def display_html(self, value, **_):
        return H(
            *(
                H.span("", cls=f"mana s{color} small mana-{value[color]}")
                for color in "wubrg"
                if value.get(color) not in (None, 0, "0")
            )
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
        return H(
            *(H.label(
                H.span("", cls=f"mana s{color} medium"),
                H.input(type="range", name=f"mana-{color}", min="0", max="5", value=str(value.get(color, 0))),
            ) for color in "wubrg")
        )

    def decode(self, encoded):
        return json.loads(encoded)

    def encode(self, value):
        return json.dumps(value)


class alpha2(DataType):
    supports_value_query = True

    def display_html(self, value, **_):
        try:
            country = pycountry.countries.lookup(value.upper())
        except LookupError:
            return H.span(f"invalid country ({value.upper()})", cls="type-alpha2")
        return H.span(
            H.a(
                f"{country.flag} {country.name}",
                href=f"/types/alpha2/{value.upper()}",
            ),
            cls="type-alpha2",
        )

    def encode(self, string):
        val = string.upper()
        if len(val) == 2 and 65 <= ord(val[0]) <= 90 and 65 <= ord(val[1]) <= 90:
            return val
        raise ValueError("Needs to be two-letter ASCII")

    def input_html(self, value=None, **_):
        if value and not isinstance(value, str):
            value = value.value
        return widget(Tags("dt=alpha2"), value=value)

    def autocomplete(self, query):
        try:
            results = pycountry.countries.search_fuzzy(query)
        except LookupError:
            results = []
        return [
            (c.alpha_2, f"{c.flag} {c.name}")
            for c in results[:5]
        ]


class age(DataType):
    def display_html(self, value, **_):
        earliest, latest = value
        if earliest == latest:
            date_range = earliest
        else:
            date_range = f"{earliest}–{latest}"
        return H(
            f"{self.possible_ages(value)} years old ",
            H.small(f"({date_range})"),
        )

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
            return H(
                H.input(name="value", value=str(self.possible_ages(value.value))),
                H.small(
                    "Format: ",
                    H.tt("optional-date:age"),
                    ". The age can also be a range. E.g.: ",
                    H.tt("2026-03-05:42-44"),
                    ". Updates restrict further.",
                ),
                H.input(type="hidden", name="previous", value=f"{earliest:%Y-%m-%d}--{latest:%Y-%m-%d}"),
            )
        else:
            return H(
                H.input(name="value"),
                H.small(
                    "Format: ",
                    H.tt("optional-date:age"),
                    ". The age can also be a range. E.g.: ",
                    H.tt("2026-03-05:42-44"),
                    ".",
                ),
            )


class daterange(DataType):
    def display_html(self, value, **_):
        earliest, latest = value
        if earliest == latest:
            date_range = str(earliest)
        elif str(earliest).endswith("-01-01") and str(latest).endswith("-12-31"):
            # full years
            if earliest.year == latest.year:
                return H(str(earliest.year))
            else:
                return H(f"{earliest.year} – {latest.year}")
        else:
            date_range = f"{earliest} – {latest}"
        # TODO: add nice form for full months as well
        return H(date_range)

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
                latest = {}
            else:
                latest = {"value": str(latest)}
            earliest = {"value": str(earliest)}
        else:
            earliest = latest = {}

        pattern = r"[0-9?]{4}-[0-9?]{2}-[0-9?]{2}"
        return H.fieldset(
            H.input(name="value_earliest", pattern=pattern, placeholder="Date, or earliest possible date", **earliest),
            H.input(value="–", style="width: 50px;", disabled=True),
            H.input(name="value_latest", pattern=pattern, placeholder="Latest date (optional)", **latest),
            role="group",
        )


class choice(DataType):
    def display_html(self, value, **_):
        return H.span(escape(value), cls="type-choice")

    def next_step(self, args):
        return H(
            H.label(
                "Enter possible choices. One choice per line.",
                H.textarea("", name="choices"),
            ),
            H.button("Create", type="submit"),
        )

    def get_extra(self, args):
        return json.dumps([choice.strip() for choice in args["choices"].split("\n") if choice.strip()])

    def detail_for(self, verb):
        choices = json.loads(verb.extra)
        return H(
            H.h4("Choices:"),
            H.ul(
                *(H.li(choice) for choice in choices)
            ),
        )

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        choices = json.loads(O.Verb(verb_id).extra)
        return H.select(
            *(H.option(str(choice), name=str(choice), selected=choice==value) for choice in choices),
            name="value",
        )

    @property
    def compatible_types(self):
        # choice and choices can't be reverbed (not even to verbs of the same
        # data type), because other verbs will have different choices
        return ()

    def edit_verb_form(self, verb):
        choices = [c.strip() for c in json.loads(verb.extra)]
        return H.label(
            "Enter possible choices. One choice per line.",
            H.textarea(
                "\n".join(choices),
                name="choices",
            ),
        )

    def edit_verb(self, verb, form):
        new_extra = self.get_extra(form)
        new = set(json.loads(new_extra))
        old = set(json.loads(verb.extra))
        if old - new:
            raise ValueError(f"Can't remove values from choice(s): {set(json.loads(new_extra)) - set(verb.extra)} (old: {old}, new: {new})")
        verb.extra = new_extra

class choices(choice):
    def display_html(self, value, **_):
        return join(", ", (H.span(escape(choice), cls="type-choice") for choice in value))

    def input_html(self, verb_id, value=None, **_):
        import veronique.objects as O
        choices = json.loads(O.Verb(verb_id).extra)
        return H.select(
            *(H.option(str(choice), name=str(choice), selected=value and choice in value.value) for choice in choices),
            name="value",
            multiple=True,
        )

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
