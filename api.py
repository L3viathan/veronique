import functools
from itertools import chain
from types import CoroutineType
from sanic import Sanic, html, file
import controller as ctrl
from property_types import TYPES

app = Sanic("Veronique")


def D(multival_dict):
    return {key: val[0] for key, val in multival_dict.items()}


with open("template.html") as f:
    TEMPLATE = f.read().format


def fragment(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ret = fn(*args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        return html(ret)
    return wrapper


def page(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ret = fn(*args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        return html(TEMPLATE(ret))
    return wrapper


def _display_created(timestamp=None):
    if timestamp:
        return f' <span class="hovercreated" style="font-size: xx-small;">created {timestamp}</span>'
    return ' <span class="hovercreated" style="font-size: xx-small;">created just now</span>'


@app.get("/")
@page
async def index(request):
    return ""


@app.get("/types")
@page
async def list_types(request):
    return "<br>".join(TYPES)


@app.get("/creatures")
@page
async def list_creatures(request):
    page = request.args.get("page", 1)
    return "<br>".join(
            f'<a hx-push-url="true" hx-get="/creatures/{id}" hx-select="#container" hx-target="#container">{name}</a>'
            for id, name in ctrl.list_creatures(page=page)
        ) + """
    <br>
    <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
    """


@app.get("/creatures/new")
@fragment
async def new_creature_form(request):
    return """
        <form hx-post="/creatures/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <button type="submit">»</button>
        </form>
    """


@app.post("/creatures/new")
@fragment
async def new_creature(request):
    name = D(request.form)["name"]
    creature_id = ctrl.add_creature(name)
    return f"""
        <a hx-push-url="true" hx-get="/creatures/{creature_id}" hx-select="#container" hx-target="#container">{name}</a>
        <br>
        <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
    """


@app.get("/creatures/<creature_id>")
@page
async def view_creature(request, creature_id: int):
    facts = ctrl.get_creature_facts(creature_id)
    name = ctrl.get_creature_name(creature_id)
    display_facts = []
    for row in chain.from_iterable(facts.values()):
        display_facts.append(
            f"<li>{row['label']}: {TYPES[row['type']].display_html(row['value'], created_at=row['created_at'])}{_display_created(row['created_at'])}</li>"
        )
    return f"""
        <h2>{name}</h2>
        <ul>
            {"".join(display_facts)}
            <button hx-get="/facts/new/{creature_id}" hx-swap="outerHTML">New fact</button>
        </ul>
    """


@app.get("/facts/new/<creature_id>")
@fragment
async def new_fact_form(request, creature_id: int):
    props = ctrl.list_properties()
    return f"""
        <form hx-post="/facts/new/{creature_id}" hx-swap="outerHTML">
            <select name="property" hx-get="/facts/new/{creature_id}/property" hx-target="#valueinput" hx-swap="innerHTML">
                <option selected disabled>--Property--</option>
                {"".join(f'''<option value="{id}">{label} <em>({type})</em></option>''' for id, label, type in props)}
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/facts/new/<creature_id>/property")
@fragment
async def new_fact_form_property_input(request, creature_id: int):
    label, type, extra_data = ctrl.get_property(int(D(request.args)["property"]))
    return f"""
        {TYPES[type].input_html(creature_id, extra_data=extra_data)}
        <button type="submit">»</button>
        """


@app.post("/facts/new/<creature_id>")
@fragment
async def new_fact(request, creature_id: int):
    form = D(request.form)
    property_id = int(form["property"])
    label, type, _ = ctrl.get_property(property_id)
    value = form.get("value")
    ctrl.add_fact(creature_id, property_id, value)
    # FIXME: replace value with value from DB
    return f"""
        <li>{label}: {TYPES[type].display_html(value, created_at=None)}{_display_created()}</li>
        <button hx-get="/facts/new/{creature_id}" hx-swap="outerHTML">New fact</button>
        """


@app.get("/properties")
@page
async def list_properties(request):
    return "<br>".join(
            f"{label} <em>({type})</em>" for id, label, type in ctrl.list_properties()
        ) + """
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
        """


@app.get("/properties/new")
@fragment
async def new_property_form(request):
    return f"""
        <form hx-post="/properties/new" hx-swap="outerHTML">
            <input name="label" placeholder="label"></input>
            <select name="type" hx-get="/properties/new/steps" hx-target="#steps" hx-swap="innerHTML">
            <option selected disabled>--Type--</option>
            {"".join(f'''<option value="{type}">{type}</option>''' for type in TYPES)}
            </select>
            <span id="steps"></span>
        </form>
    """


@app.get("/properties/new/steps")
@fragment
async def new_property_form_steps(request):
    args = D(request.args)
    type = TYPES[args["type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">»</button>'


@app.post("/properties/new")
@fragment
async def new_property(request):
    form = D(request.form)
    type = TYPES[form["type"]]
    ctrl.add_property(
        form["label"],
        form["type"],
        reflected_property_name=(
            None
            if form.get("reflectivity", "none") == "none"
            else ctrl.SELF
            if form["reflectivity"] == "self"
            else form["inversion"]
        ),
        extra_data=type.encode_extra_data(form),
    )
    return f"""
        {form['label']} <em>({form['type']})</em>
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
    """


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")
