from datetime import date as datetime_date
import controller as ctrl

TYPES = {}


class PropertyType:
    def __init_subclass__(cls):
        TYPES[cls.__name__] = cls()

    def display_html(self, value):
        return f"placeholder, not implemented for type {type(self).__name__}."

    def input_html(self, creature_id):
        return f"placeholder, not implemented for type {type(self).__name__}."


class string(PropertyType):
    def display_html(self, value):
        return f'<span style="color: lime;">"{value}"</span>'

    def input_html(self, creature_id):
        return """<input type="text" name="value"></input>"""

class creature(PropertyType):
    def display_html(self, value):
        name = ctrl.get_creature_name(value)
        return f'<a hx-target="#container" hx-get="/creatures/{value}">🔗 {name}</a>'

    def input_html(self, creature_id):
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

class number(PropertyType):
    def display_html(self, value):
        return f'<span style="color: orange">{value}</span>'

    def input_html(self, creature_id):
        return """<input type="number" step="any" name="value"></input>"""


class color(PropertyType):
    def display_html(self, value):
        return f"""
            <span style="color: {value}; text-shadow: 0 0 3px black;">&#9632;</span>
            {value}
        """

    def input_html(self, creature_id):
        return """<input type="color" name="value"></input>"""


class date(PropertyType):
    def display_html(self, value):
        d = datetime_date.fromisoformat(value)
        today = datetime_date.today()
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

    def input_html(self, creature_id):
        return """<input type="date" name="value"></input>"""
