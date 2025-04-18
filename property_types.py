import json
import datetime
import unicodedata
from urllib.parse import quote_plus

import objects as O
from nomnidate import NonOmniscientDate

TYPES = {}

def float_int(val):
    val = float(val)
    if val.is_integer():
        val = int(val)
    return val


# these are the data_types
class PropertyType:
    def __init_subclass__(cls):
        TYPES[cls.__name__] = cls()

    def display_html(self, value, **_):
        return f"placeholder, not implemented for property type {type(self).__name__}."

    def input_html(self, entity, prop, value=None):
        return f"placeholder, not implemented for property type {type(self).__name__}."

    def next_step(self, args):
        return None

    def encode_extra_data(self, form):
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

    def __str__(self):
        return f"<em>{self.name}</em>"

    @property
    def name(self):
        return type(self).__name__


class entity(PropertyType):
    def display_html(self, value, **_):
        raise RuntimeError("How did we end up here? Entities are displayed differently")

    def input_html(self, entity, prop, value=None):
        parts = []
        if value is not None:
            value_maybe = f"""value="{value.name}" """
            hidden_input = """<input type="hidden" name="value" value="{value.id}">"""
        else:
            value_maybe = ""
            hidden_input = ""
        return f"""
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="Start typing..."
                    hx-get="/entities/autocomplete/{prop.object_category.id}"
                    hx-target="next .ac-results"
                    hx-swap="innerHTML"
                    hx-trigger="input changed delay:200ms, search"
                    {value_maybe}
                >
                {hidden_input}
                <div class="ac-results">
                </div>
            </div>
        """

    def next_step(self, args):
        category_options = []
        for category in O.Category.all():
            category_options.append(
                f'<option value="{category.id}">{category}</option>',
            )
        if "reflectivity" in args:
            if args["reflectivity"] in ("none", "self"):
                return None
            return """
                <input name="inversion"></input>
                <button type="submit">»</button>
            """
        return f"""
            <select name="object_category">
                <option selected disabled>--Object--</option>
                {"".join(category_options)}
            </select>
            <select
                name="reflectivity"
                hx-get="/properties/new/steps"
                hx-target="#step2"
                hx-swap="innerHTML"
                hx-include="[name='data_type']"
            >
                <option selected disabled>--Reflectivity--</option>
                <option value="none">unidirectional</option>
                <option value="self">self-reflected</option>
                <option value="other">reflected</option>
            </select>
            <span id="step2"></span>
        """


class string(PropertyType):
    def display_html(self, value, **_):
        return f'<span class="type-string">"{value}"</span>'

    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="text" name="value"{value}></input>"""


class number(PropertyType):
    def display_html(self, value, **_):
        return f'<span class="type-number">{value}</span>'

    def input_html(self, entity, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="number" step="any" name="value"{value}></input>"""

    def decode(self, encoded):
        return float_int(encoded)


class color(PropertyType):
    def display_html(self, value, **_):
        return f"""
            <span style="color: {value}; text-shadow: 0 0 3px black;">&#9632;</span>
            {value}
        """

    def input_html(self, entity, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="color" name="value"{value}></input>"""


class date(PropertyType):
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

    def input_html(self, entity, prop, value=None):
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


class boolean(PropertyType):
    def display_html(self, value, **_):
        if value:
            return """<span style="color: green">✔</span>"""
        else:
            return """<span style="color: red">✘</span>"""

    def input_html(self, entity, prop, value=None):
        checked = " checked" if value and value.value else ""
        return f"""<input type="checkbox" name="value"{checked}></input>"""

    def encode(self, value):
        return value or "off"

    def decode(self, value):
        return value == "on"


class enum(PropertyType):
    def display_html(self, value, **_):
        return f"""<span style="color: #be5128;">{value}</span>"""

    def input_html(self, entity, prop, value=None):
        return "\n".join(
            f"""
            <input
                type="radio"
                id="choice-{n}"
                name="value"
                value="{choice}"
                {"checked" if value and choice == value.value else ""}
            ><label for="choice-{n}">{choice}</label></input>
            """ for n, choice in enumerate(prop.extra_data.split(","))
        )

    def next_step(self, args):
        return """
            <input name="choices" placeholder="choices, comma-separated"></input>
            <button type="submit">»</button>
        """

    def encode_extra_data(self, form):
        return form["choices"]


class age(PropertyType):
    def display_html(self, value, *, fact, **_):
        now = datetime.datetime.now()
        created_at = datetime.datetime.fromisoformat(fact.created_at)
        years_passed = (now - created_at).days // 365
        value += years_passed
        if now.day == created_at.day:
            return f"""<span style="color: #2889be;">{value}</span>"""
        return f"""<span style="color: #2889be;">{value}?</span>"""

    def input_html(self, entity, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""
            <input type="number" min=0 name="value"{value}></input>
        """

    def decode(self, encoded):
        return float_int(encoded)


class location(PropertyType):
    def display_html(self, value, **_):
        newline = "\n"
        return f"""<a
            href="https://www.openstreetmap.org/search?query={quote_plus(
                value.replace(newline, ", ")
            )}"
            class="type-location"
        >{value.replace(newline, "<br>")}</a>"""

    def input_html(self, entity, prop, value=None):
        if value:
            value = value.value
        else:
            value = ""
        return f"""
            <textarea name="value">{value}</textarea>
        """


class text(PropertyType):
    def display_html(self, value, **_):
        newline = "\n"
        return f"""<span class="type-text">{value.replace(newline, "<br>")}</span>"""

    def input_html(self, entity, prop, value=None):
        if value:
            value = value.value
        else:
            value = ""
        return f"""
            <textarea name="value">{value}</textarea>
        """


class email(PropertyType):
    def display_html(self, value, **_):
        return f'<span class="type-email"><a href="mailto:{value}">{value}</a></span>'

    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="email" name="value"{value}></input>"""


class website(PropertyType):
    def display_html(self, value, **_):
        return f'<span class="type-website"><a href="{value}">{value}</a></span>'

    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="url" name="value"{value}></input>"""


class phonenumber(PropertyType):
    def display_html(self, value, **_):
        return f"""<span
            class="type-phonenumber"
        >
            <a href="tel:{value}">{value}</a>
        </span>"""

    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="tel" name="value"{value}></input>"""


class picture(PropertyType):
    def display_html(self, value, **_):
        return f'<img class="type-picture" src="{value}">'

    def input_html(self, entity, prop, value=None):
        return """<input name="value" type="file"></input>"""


class social(PropertyType):
    def display_html(self, value, prop, **_):
        link = prop.extra_data.format(value)
        return f'<span class="type-social"><a href="{link}">{value}</a></span>'

    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
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

    def encode_extra_data(self, form):
        return form["template"]


class mtgcolors(PropertyType):
    def display_html(self, value, prop, **_):
        return "".join(
            f'<span class="mana s{color} small mana-{value[color]}"></span>'
            for color in "wubrg"
            if value.get(color) not in (None, 0, "0")
        )

    def extract_value(self, form):
        return {
            color: int(form[f"mana-{color}"])
            for color in "wubrg"
            if int(form[f"mana-{color}"]) != 0
        }

    def input_html(self, entity, prop, value=None):
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


class alpha2(PropertyType):
    def display_html(self, value, prop, **_):
        country = value.upper()
        flag = "".join(
            unicodedata.lookup(
                f"REGIONAL INDICATOR SYMBOL LETTER {c}"
            )
            for c in country
        )
        return f'<span class="type-alpha2">{flag} {country}</span>'

    def encode(self, string):
        val = string.upper()
        if (
            len(val) == 2
            and 65 <= ord(val[0]) <= 90
            and 65 <= ord(val[1]) <= 90
        ):
            return val
        raise ValueError("Needs to be two-letter ASCII")


    def input_html(self, entity, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input name="value"{value}></input>"""
