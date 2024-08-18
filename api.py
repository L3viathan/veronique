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


@app.get("/entity-types")
@page
async def list_types(request):
    types = ctrl.list_entity_types()
    return "<br>".join(name for _, name in types) + """
    <br>
    <button hx-get="/entity-types/new" hx-swap="outerHTML">New entity type</button>
    """


@app.get("/entity-types/new")
@fragment
async def new_entity_type_form(request):
    types = ctrl.list_entity_types()
    return f"""
        <form hx-post="/entity-types/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <button type="submit">»</button>
        </form>
    """


@app.post("/entity-types/new")
@fragment
async def new_entity_type(request):
    form = D(request.form)
    name = form["name"]
    entity_id = ctrl.add_entity_type(name)
    return f"""
        {name}
        <br>
        <button hx-get="/entity-types/new" hx-swap="outerHTML">New entity type</button>
    """


@app.get("/entities")
@page
async def list_entities(request):
    page = request.args.get("page", 1)
    return "<br>".join(
            f'<a hx-push-url="true" hx-get="/entities/{id}" hx-select="#container" hx-target="#container">{name}</a>'
            for id, name in ctrl.list_entities(page=page)
        ) + """
    <br>
    <button hx-get="/entities/new" hx-swap="outerHTML">New entity</button>
    """


@app.get("/entities/new")
@fragment
async def new_entity_form(request):
    types = ctrl.list_entity_types()
    return f"""
        <form hx-post="/entities/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <select name="entity_type">
                <option selected disabled>--Entity Type--</option>
                {"".join(f'''<option value="{choice_id}">{choice}</option>''' for choice_id, choice in types)}
            </select>
            <button type="submit">»</button>
        </form>
    """


@app.post("/entities/new")
@fragment
async def new_entity(request):
    form = D(request.form)
    name = form["name"]
    entity_id = ctrl.add_entity(name, form["entity_type"])
    return f"""
        <a hx-push-url="true" hx-get="/entities/{entity_id}" hx-select="#container" hx-target="#container">{name}</a>
        <br>
        <button hx-get="/entities/new" hx-swap="outerHTML">New entity</button>
    """


@app.get("/entities/<entity_id>")
@page
async def view_entity(request, entity_id: int):
    facts = ctrl.get_entity_facts(entity_id)
    name, _entity_type = ctrl.get_entity(entity_id)
    display_facts = []
    for row in chain.from_iterable(facts.values()):
        display_facts.append(
            f"<li>{row['label']}: {TYPES[row['data_type']].display_html(row['value'], created_at=row['created_at'])}{_display_created(row['created_at'])}</li>"
        )
    return f"""
        <h2>{name}</h2>
        <ul>
            {"".join(display_facts)}
            <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
        </ul>
    """


@app.get("/facts/new/<entity_id>")
@fragment
async def new_fact_form(request, entity_id: int):
    name, entity_type = ctrl.get_entity(entity_id)
    props = ctrl.list_properties(subject_type_id=entity_type)
    return f"""
        <form hx-post="/facts/new/{entity_id}" hx-swap="outerHTML">
            <select name="property" hx-get="/facts/new/{entity_id}/property" hx-target="#valueinput" hx-swap="innerHTML">
                <option selected disabled>--Property--</option>
                {"".join(f'''<option value="{id}">{label} <em>({type})</em></option>''' for id, label, type in props)}
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/facts/new/<entity_id>/property")
@fragment
async def new_fact_form_property_input(request, entity_id: int):
    prop = ctrl.get_property(int(D(request.args)["property"]))
    return f"""
        {TYPES[prop["data_type"]].input_html(entity_id, prop)}
        <button type="submit">»</button>
        """


@app.post("/facts/new/<entity_id>")
@fragment
async def new_fact(request, entity_id: int):
    form = D(request.form)
    property_id = int(form["property"])
    prop = ctrl.get_property(property_id)
    value = form.get("value")
    ctrl.add_fact(entity_id, property_id, value)
    # FIXME: replace value with value from DB
    return f"""
        <li>{prop["label"]}: {TYPES[prop["data_type"]].display_html(value, created_at=None)}{_display_created()}</li>
        <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
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
    type_options = []
    for type_id, name in ctrl.list_entity_types():
        type_options.append(f'<option value="{type_id}">{name}</option>')
    return f"""
        <form hx-post="/properties/new" hx-swap="outerHTML">
            <select name="subject_type">
                <option selected disabled>--Subject--</option>
                {"".join(type_options)}
            </select>
            <input name="label" placeholder="label"></input>
            <select name="data_type" hx-get="/properties/new/steps" hx-target="#steps" hx-swap="innerHTML">
                <option selected disabled>--Type--</option>
                {"".join(f'''<option value="{data_type}">{data_type}</option>''' for data_type in TYPES)}
            </select>
            <span id="steps"></span>
        </form>
    """


@app.get("/properties/new/steps")
@fragment
async def new_property_form_steps(request):
    args = D(request.args)
    print(args)
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">»</button>'


@app.post("/properties/new")
@fragment
async def new_property(request):
    form = D(request.form)
    type = TYPES[form["data_type"]]
    ctrl.add_property(
        form["label"],
        form["data_type"],
        reflected_property_name=(
            None
            if form.get("reflectivity", "none") == "none"
            else ctrl.SELF
            if form["reflectivity"] == "self"
            else form["inversion"]
        ),
        subject_type_id=form["subject_type"],
        object_type_id=form.get("object_type"),
        extra_data=type.encode_extra_data(form),
    )
    return f"""
        {form['label']} <em>({form['data_type']})</em>
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
    """


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")
