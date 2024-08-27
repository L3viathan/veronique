import datetime
from urllib.parse import quote_plus
import objects as O

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

    def display_html(self, value):
        return f"placeholder, not implemented for property type {type(self).__name__}."

    def input_html(self, entity_id, prop, value=None):
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
    def display_html(self, value):
        raise RuntimeError("How did we end up here? Entities are displayed differently")

    def input_html(self, entity_id, prop, value=None):
        # this won't scale, but good enough for now
        # FIXME: why do we get the entity_id here, not the entity?
        parts = []
        for entity in O.Entity.all(entity_type=prop.object_type):
            if entity.id == entity_id:
                continue
            if value and entity.id == value.id:
                selected = " selected"
                default_selected = ""
            else:
                selected = ""
                default_selected = " selected"
            parts.append(
                f'<option{selected} value="{entity.id}">{entity.name}</option>',
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
    def display_html(self, value):
        return f'<span class="type-string">"{value}"</span>'

    def input_html(self, entity_id, prop, value=None):
        if value:
            quot = '"'
            value = f' value="{value.value.replace(quot, "&quot;")}"'
        else:
            value = ""
        return f"""<input type="text" name="value"{value}></input>"""


class number(PropertyType):
    def display_html(self, value):
        return f'<span class="type-number">{value}</span>'

    def input_html(self, entity_id, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="number" step="any" name="value"{value}></input>"""

    def decode(self, encoded):
        return float_int(encoded)


class color(PropertyType):
    def display_html(self, value, created_at=None):
        return f"""
            <span style="color: {value}; text-shadow: 0 0 3px black;">&#9632;</span>
            {value}
        """

    def input_html(self, entity_id, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="color" name="value"{value}></input>"""


class date(PropertyType):
    def display_html(self, value):
        d = datetime.date.fromisoformat(value)
        today = datetime.date.today()
        td = today - d
        postposition = "ago" if abs(td) == td else "from now"
        years = td.days // 365
        today_that_year = today.replace(year=d.year)
        days = -(today_that_year - d).days
        if years and days:
            context = f"{abs(years)} years {postposition} {days:+} days"
        elif years:
            context = f"{abs(years)} years {postposition} today"
        elif days:
            context = f"{days} days {postposition}"
        else:
            context = "today"
        return f"🗓️{value} <em>({context})</em>"

    def input_html(self, entity_id, prop, value=None):
        if value:
            value = f' value="{value.value}"'
        else:
            value = ""
        return f"""<input type="date" name="value"{value}></input>"""


class boolean(PropertyType):
    def display_html(self, value):
        if value:
            return """<span style="color: green">✔</span>"""
        else:
            return """<span style="color: red">✘</span>"""

    def input_html(self, entity_id, prop, value=None):
        checked = " checked" if value and value.value else ""
        return f"""<input type="checkbox" name="value"{checked}></input>"""

    def encode(self, value):
        return value or "off"

    def decode(self, value):
        return value == "on"


class enum(PropertyType):
    def display_html(self, value):
        return f"""<span style="color: #be5128;">{value}</span>"""

    def input_html(self, entity_id, prop, value=None):
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
    def display_html(self, value):
        # TODO: fix this, it was broken for a while.
        # Perhaps a plain value knows about its fact?
        # now = datetime.datetime.now()
        # years_passed = (now - created_at).days // 365
        # value += years_passed
        # if now.day == created_at.day:
        #     return f"""<span style="color: #2889be;">{value}</span>"""
        return f"""<span style="color: #2889be;">{value}?</span>"""

    def input_html(self, entity_id, prop, value=None):
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
    def display_html(self, value):
        newline = "\n"
        return f"""<a href="https://www.openstreetmap.org/search?query={quote_plus(value.replace(newline, ", "))}" class="type-location">{value.replace(newline, "<br>")}</a>"""

    def input_html(self, entity_id, prop, value=None):
        if not value:
            value = ""
        return f"""
            <textarea name="value">{value.value}</textarea>
        """
