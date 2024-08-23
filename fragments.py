from property_types import TYPES


def created_ts(timestamp=None):
    if timestamp:
        return f' <span class="hovercreated" style="font-size: xx-small;">created {timestamp}</span>'
    return ' <span class="hovercreated" style="font-size: xx-small;">created just now</span>'


def label(row):
    return f"""<a
        hx-get="/properties/{row["property_id"]}"
        hx-push-url="true"
        hx-select="#container"
        hx-target="#container"
    class="property">{row["label"]}</a>"""


def vp(row):
    row = dict(row)
    return f'<span class="vp">{label(row)}{TYPES[row["data_type"]].display_html(row["value"], created_at=row.get("created_at"))}</span>{created_ts(row.get("created_at"))}'


def fact(row):
    row = dict(row)
    return f'<span class="fact">{TYPES["entity"].display_html(row["subject_id"])}{vp(row)}</span>'


def property(row, entity_types):
    subject_type = entity_types[row["subject_type_id"]]
    if row["data_type"] == "entity":
        object_type = entity_types[row["object_type_id"]]
        object_part = f'<strong>{object_type}</strong>'
    else:
        object_part = f'<em>{row["data_type"]}</em>'
    return f"""<a
        hx-push-url="true"
        hx-get="/properties/{row["id"]}"
        hx-select="#container"
        hx-target="#container"
    ><strong>{subject_type}</strong> {row["label"]} {object_part}</a>"""
