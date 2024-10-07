import datetime
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
        return str(value)

    def decode(self, encoded):
        return str(encoded)

    def __str__(self):
        return f"<em>{self.name}</em>"

    @property
    def name(self):
        return type(self).__name__


class entity(PropertyType):
    def display_html(self, value, **_):
        raise RuntimeError("How did we end up here? Entities are displayed differently")

    def input_html(self, entity, prop, value=None):
        # this won't scale, but good enough for now
        parts = []
        for other_entity in O.Entity.all(entity_type=prop.object_type):
            if other_entity == entity:
                continue
            if value and other_entity.id == value.id:
                selected = " selected"
                default_selected = ""
            else:
                selected = ""
                default_selected = " selected"
            parts.append(
                f'<option{selected} value="{other_entity.id}">{other_entity.name}</option>',
            )
        return f"""
            <select name="value">
                <option{default_selected} disabled>--Entity--</option>
                {"".join(parts)}
            </select>
        """

    def next_step(self, args):
        type_options = []
        for entity_type in O.EntityType.all():
            type_options.append(f'<option value="{entity_type.id}">{entity_type}</option>')
        if "reflectivity" in args:
            if args["reflectivity"] in ("none", "self"):
                return None
            return """
                <input name="inversion"></input>
                <button type="submit">»</button>
            """
        return f"""
            <select name="object_type">
                <option selected disabled>--Object--</option>
                {"".join(type_options)}
            </select>
            <select name="reflectivity" hx-get="/properties/new/steps" hx-target="#step2" hx-swap="innerHTML" hx-include="[name='data_type']">
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
        return f"🗓️{value} <em>({td})</em>"

    def input_html(self, entity, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="text" size=10 pattern="([0-9?]{4}-[0-9?]{2}-[0-9?]{2}" name="value"{value}></input>"""


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
            <input type="radio" id="choice-{n}" name="value" value="{choice}" {"checked" if value and choice == value.value else ""}><label for="choice-{n}">{choice}</label></input>
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
    def display_html(self, value, **_):
        # TODO: fix this, it was broken for a while.
        # Perhaps a plain value knows about its fact?
        # now = datetime.datetime.now()
        # years_passed = (now - created_at).days // 365
        # value += years_passed
        # if now.day == created_at.day:
        #     return f"""<span style="color: #2889be;">{value}</span>"""
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
