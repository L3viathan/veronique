import functools
from itertools import chain, groupby
from types import CoroutineType
from sanic import Sanic, html, file
import controller as ctrl
import fragments as F
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


@app.get("/")
@page
async def index(request):
    return ""


@app.get("/entity-types")
@page
async def list_types(request):
    types = ctrl.list_entity_types()
    return "<br>".join(f"<strong>{name}</strong>" for _, name in types) + """
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
    entity_types = {
        row["id"]: row["name"]
        for row in ctrl.list_entity_types()
    }
    parts = []
    for entity_type_id, group in groupby(ctrl.list_entities(page=page), lambda x: x["entity_type_id"]):
        parts.append(f"<h2>{entity_types[entity_type_id]}</h2>")
        for i, row in enumerate(group):
            if i:
                parts.append("<br>")
            parts.append(
                f"""
                <a
                    class="clickable entity-link"
                    hx-push-url="true"
                    hx-get="/entities/{row["id"]}"
                    hx-select="#container"
                    hx-target="#container">{row["name"]}</a>
                """,
            )
    parts.append("""<br><button hx-get="/entities/new" hx-swap="outerHTML">New entity</button>""")
    return "".join(parts)


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
    facts = ctrl.list_facts(entity_id=entity_id)
    name, _entity_type = ctrl.get_entity(entity_id)
    display_facts = []
    for row in facts:
        display_facts.append(
            f"<li>{F.vp(row)}</li>",
        )
    return f"""
        <h2>{name}</h2>
        <ul>
            {"".join(display_facts)}
            <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
        </ul>
    """

@app.get("/properties/<property_id>")
@page
async def view_property(request, property_id: int):
    prop = ctrl.get_property(property_id)
    parts = [f"""<h2>{prop["label"]}</h2>"""]
    for row in ctrl.list_facts(property_id=property_id):
        parts.append(F.fact(row))
    return "".join(parts)


@app.get("/facts/new/<entity_id>")
@fragment
async def new_fact_form(request, entity_id: int):
    name, entity_type = ctrl.get_entity(entity_id)
    props = ctrl.list_properties(subject_type_id=entity_type)
    return f"""
        <form hx-post="/facts/new/{entity_id}" hx-swap="outerHTML">
            <select name="property" hx-get="/facts/new/{entity_id}/property" hx-target="#valueinput" hx-swap="innerHTML">
                <option selected disabled>--Property--</option>
                {"".join(f'''<option value="{row["id"]}">{row["label"]} <em>({row["data_type"]})</em></option>''' for row in props)}
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
    fact_id = ctrl.add_fact(entity_id, property_id, value)
    fact = ctrl.get_fact(fact_id)
    # FIXME: replace value with value from DB
    return f"""
        <li>{F.vp(fact)}</li>
        <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
    """


@app.get("/properties")
@page
async def list_properties(request):
    entity_types = {
        row["id"]: row["name"]
        for row in ctrl.list_entity_types()
    }
    parts = []
    for row in ctrl.list_properties():
        parts.append(F.property(row, entity_types))

    parts.append("""<button hx-get="/properties/new" hx-swap="outerHTML">New property</button>""")
    return "<br>".join(parts)


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
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">»</button>'


@app.post("/properties/new")
@fragment
async def new_property(request):
    form = D(request.form)
    type = TYPES[form["data_type"]]
    property_id = ctrl.add_property(
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
    entity_types = {
        row["id"]: row["name"]
        for row in ctrl.list_entity_types()
    }
    row = ctrl.get_property(property_id)
    return f"""
        {F.property(row, entity_types)}
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
    """


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")


@app.get("/style.css")
async def style_css(request):
    return await file("style.css", mime_type="text/css")
