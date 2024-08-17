import datetime
import controller as ctrl

TYPES = {}


class PropertyType:
    def __init_subclass__(cls):
        TYPES[cls.__name__] = cls()

    def display_html(self, value, created_at=None):
        return f"placeholder, not implemented for type {type(self).__name__}."

    def input_html(self, creature_id, extra_data):
        return f"placeholder, not implemented for type {type(self).__name__}."

    def next_step(self, args):
        return None

    def encode_extra_data(self, form):
        return None


class string(PropertyType):
    def display_html(self, value, created_at=None):
        return f'<span style="color: #57e389;">"{value}"</span>'

    def input_html(self, creature_id, extra_data):
        return """<input type="text" name="value"></input>"""


class creature(PropertyType):
    def display_html(self, value, created_at=None):
        name = ctrl.get_creature_name(value)
        return f'<a hx-push-url="true" hx-select="#container" hx-target="#container" hx-get="/creatures/{value}">🔗 {name}</a>'

    def input_html(self, creature_id, extra_data):
        # this won't scale, but good enough for now
        parts = []
        for other_creature_id, name in ctrl.list_creatures():
            if other_creature_id == creature_id:
                continue
            parts.append(
                f'<option value="{other_creature_id}">{name}</option>',
            )
        return f"""
            <select name="value">
                <option selected disabled>--Creature--</option>
                {"".join(parts)}
            </select>
        """

    def next_step(self, args):
        if "reflectivity" in args:
            if args["reflectivity"] in ("none", "self"):
                return None
            return """
                <input name="inversion"></input>
                <button type="submit">»</button>
            """
        return """
            <select name="reflectivity" hx-get="/properties/new/steps" hx-target="#step2" hx-swap="innerHTML" hx-include="[name='type']">
                <option selected disabled>--Reflectivity--</option>
                <option value="none">unidirectional</option>
                <option value="self">self-reflected</option>
                <option value="other">reflected</option>
            </select>
            <span id="step2"></span>
        """


class number(PropertyType):
    def display_html(self, value, created_at=None):
        return f'<span style="color: orange">{value}</span>'

    def input_html(self, creature_id, extra_data):
        return """<input type="number" step="any" name="value"></input>"""


class color(PropertyType):
    def display_html(self, value, created_at=None):
        return f"""
            <span style="color: {value}; text-shadow: 0 0 3px black;">&#9632;</span>
            {value}
        """

    def input_html(self, creature_id, extra_data):
        return """<input type="color" name="value"></input>"""


class date(PropertyType):
    def display_html(self, value, created_at=None):
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

    def input_html(self, creature_id, extra_data):
        return """<input type="date" name="value"></input>"""


class boolean(PropertyType):
    def display_html(self, value, created_at=None):
        if value:
            return """<span style="color: green">✔</span>"""
        else:
            return """<span style="color: red">✘</span>"""

    def input_html(self, creature_id, extra_data):
        return """<input type="checkbox" name="value"></input>"""


class enum(PropertyType):
    def display_html(self, value, created_at=None):
        return f"""<span style="color: #be5128;">{value}</span>"""

    def input_html(self, creature_id, extra_data):
        return "\n".join(
            f"""
            <input type="radio" id="choice-{n}" name="value" value="{choice}"><label for="choice-{n}">{choice}</label></input>
            """ for n, choice in enumerate(extra_data.split(","))
        )

    def next_step(self, args):
        return """
            <input name="choices" placeholder="choices, comma-separated"></input>
            <button type="submit">»</button>
        """

    def encode_extra_data(self, form):
        return form["choices"]


class age(PropertyType):
    def display_html(self, value, created_at=None):
        if not created_at:
            return f"""<span style="color: #2889be;">{value}</span>"""
        now = datetime.datetime.now()
        years_passed = (now - created_at).days // 365
        value += years_passed
        if now.day == created_at.day:
            return f"""<span style="color: #2889be;">{value}</span>"""
        return f"""<span style="color: #2889be;">{value}?</span>"""

    def input_html(self, creature_id, extra_data):
        return """
            <input type="number" min=0 name="value"></input>
        """
