from property_types import TYPES


def created_ts(timestamp=None):
    if timestamp:
        return f' <span class="hovercreated" style="font-size: xx-small;">created {timestamp}</span>'
    return ' <span class="hovercreated" style="font-size: xx-small;">created just now</span>'


def fact(row):
    row = dict(row)
    return f"{row['label']}: {TYPES[row['data_type']].display_html(row['value'], created_at=row.get('created_at'))}{created_ts(row.get('created_at'))}"
