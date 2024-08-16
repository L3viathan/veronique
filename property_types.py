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
                {"".join(parts)}
            </select>
        """
