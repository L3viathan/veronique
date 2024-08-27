import os
import functools
import base64
from itertools import chain, groupby
from types import CoroutineType
from sanic import Sanic, HTTPResponse, html, file
import objects as O
from property_types import TYPES

app = Sanic("Veronique")

@app.on_request
async def auth(request):
    try:
        correct_auth = os.environ["VERONIQUE_CREDS"]
        auth = request.headers["Authorization"]
        _, _, encoded = auth.partition(" ")
        if base64.b64decode(encoded).decode() != correct_auth:
            raise ValueError
    except (KeyError, AssertionError, ValueError):
        return HTTPResponse(
            body="401 Unauthorized",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Veronique access"'},
        )


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
    types = O.EntityType.all()
    return "<br>".join(str(type_) for type_ in types) + """
    <br>
    <button hx-get="/entity-types/new" hx-swap="outerHTML">New entity type</button>
    """


@app.get("/entity-types/new")
@fragment
async def new_entity_type_form(request):
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
    entity_type = O.EntityType.new(name)
    return f"""
        {entity_type}
        <br>
        <button hx-get="/entity-types/new" hx-swap="outerHTML">New entity type</button>
    """


@app.get("/entities")
@page
async def list_entities(request):
    page = request.args.get("page", 1)  # TODO
    parts = []
    for i, entity in enumerate(O.Entity.all()):
        if i:
            parts.append("<br>")
        parts.append(f"{entity:full}")
    parts.append("""<br><button hx-get="/entities/new" hx-swap="outerHTML">New entity</button>""")
    return "".join(parts)


@app.get("/entities/new")
@fragment
async def new_entity_form(request):
    types = O.EntityType.all()
    return f"""
        <form hx-post="/entities/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <select name="entity_type">
                <option selected disabled>--Entity Type--</option>
                {"".join(f'''<option value="{et.id}">{et.name}</option>''' for et in types)}
            </select>
            <button type="submit">»</button>
        </form>
    """


@app.post("/entities/new")
@fragment
async def new_entity(request):
    form = D(request.form)
    name = form["name"]
    entity = O.Entity.new(name, O.Entity(int(form["entity_type"])))
    return f"""
        {entity}
        <br>
        <button hx-get="/entities/new" hx-swap="outerHTML">New entity</button>
    """


@app.get("/entities/<entity_id>")
@page
async def view_entity(request, entity_id: int):
    entity = O.Entity(entity_id)
    return f"""
        {entity:heading}
        <ul>
            {"".join(f"<li>{fact:short}</li>" for fact in entity.facts)}
            <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
        </ul>
        <h3>References</h3>
        <ul>
            {"".join(f"<li>{fact}</li>" for fact in entity.incoming_facts)}
        </ul>
    """

@app.get("/entity-types/<entity_type_id>")
@page
async def view_entity_type(request, entity_type_id: int):
    entity_type = O.EntityType(entity_type_id)
    entities = O.Entity.all(entity_type=entity_type)
    return f"""
        {entity_type:heading}
        <ul>
            {"".join(f"<li>{entity}</li>" for entity in entities)}
        </ul>
    """


@app.get("/entity-types/<entity_type_id>/rename")
@fragment
async def rename_entity_type_form(request, entity_type_id: int):
    entity_type = O.EntityType(entity_type_id)
    return f"{entity_type:rename-form}"


@app.post("/entity-types/<entity_type_id>/rename")
@fragment
async def rename_entity_type(request, entity_type_id: int):
    entity_type = O.EntityType(entity_type_id)
    name = D(request.form)["name"]
    if name:
        entity_type.rename(name)
    return f"{entity_type:heading}"


@app.get("/entities/<entity_id>/rename")
@fragment
async def rename_entity_form(request, entity_id: int):
    entity = O.Entity(entity_id)
    return f"{entity:rename-form}"


@app.post("/entities/<entity_id>/rename")
@fragment
async def rename_entity(request, entity_id: int):
    entity = O.Entity(entity_id)
    name = D(request.form)["name"]
    if name:
        entity.rename(name)
    return f"{entity:heading}"


@app.get("/properties/<property_id>")
@page
async def view_property(request, property_id: int):
    prop = O.Property(property_id)
    parts = [f"{prop:heading}"]
    for fact in prop.facts:
        parts.append(str(fact))
    return "".join(parts)


@app.get("/properties/<property_id>/rename")
@fragment
async def rename_property_form(request, property_id: int):
    prop = O.Property(property_id)
    return f"{prop:rename-form}"


@app.post("/properties/<property_id>/rename")
@fragment
async def rename_property(request, property_id: int):
    prop = O.Property(property_id)
    name = D(request.form)["name"]
    if name:
        prop.rename(name)
    return f"{prop:heading}"


@app.get("/facts/new/<entity_id>")
@fragment
async def new_fact_form(request, entity_id: int):
    entity = O.Entity(entity_id)
    props = O.Property.all(subject_type=entity.entity_type)
    return f"""
        <form hx-post="/facts/new/{entity_id}" hx-swap="outerHTML">
            <select name="property" hx-get="/facts/new/{entity_id}/property" hx-target="#valueinput" hx-swap="innerHTML">
                <option selected disabled>--Property--</option>
                {"".join(f'''<option value="{prop.id}">{prop.label} ({prop.data_type})</option>''' for prop in props)}
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/facts/new/<entity_id>/property")
@fragment
async def new_fact_form_property_input(request, entity_id: int):
    prop = O.Property(int(D(request.args)["property"]))
    return f"""
        {prop.data_type.input_html(entity_id, prop)}
        <button type="submit">»</button>
        """


@app.get("/facts/<fact_id>/edit")
@fragment
async def edit_fact_form(request, fact_id: int):
    fact = O.Fact(fact_id)
    return f"""
        <form hx-post="/facts/{fact_id}/edit" hx-swap="outerHTML">
            {fact.prop.data_type.input_html(fact.subj.id, fact.prop, value=fact.obj)}
            <button type="submit">»</button>
        </form>
        """


@app.post("/facts/<fact_id>/edit")
@fragment
async def edit_fact(request, fact_id: int):
    form = D(request.form)
    fact = O.Fact(fact_id)
    value = form.get("value")
    if fact.prop.data_type.name == "entity":
        value = O.Entity(int(value))
    else:
        value = O.Plain(value, fact.prop.data_type)
    fact.set_value(value)
    return f"{fact.obj}"


@app.post("/facts/new/<entity_id>")
@fragment
async def new_fact(request, entity_id: int):
    form = D(request.form)
    prop = O.Property(int(form["property"]))
    value = form.get("value")
    if prop.data_type.name == "entity":
        value = O.Entity(int(value))
    else:
        value = O.Plain(value, prop.data_type)
    fact = O.Fact.new(O.Entity(entity_id), prop, value)
    return f"""
        <li>{fact:short}</li>
        <button hx-get="/facts/new/{entity_id}" hx-swap="outerHTML">New fact</button>
    """


@app.get("/properties")
@page
async def list_properties(request):
    parts = [f"{prop:full}" for prop in O.Property.all()]
    parts.append("""<button hx-get="/properties/new" hx-swap="outerHTML">New property</button>""")
    return "<br>".join(parts)


@app.get("/properties/new")
@fragment
async def new_property_form(request):
    type_options = []
    for entity_type in O.EntityType.all():
        type_options.append(f'<option value="{entity_type.id}">{entity_type}</option>')
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
    data_type = TYPES[form["data_type"]]
    prop = O.Property.new(
        form["label"],
        data_type=data_type,
        reflected_property_name=(
            None
            if form.get("reflectivity", "none") == "none"
            else O.SELF
            if form["reflectivity"] == "self"
            else form["inversion"]
        ),
        subject_type=O.EntityType(int(form["subject_type"])),
        object_type=O.EntityType(int(form["object_type"])) if "object_type" in form else None,
        extra_data=data_type.encode_extra_data(form),
    )
    return f"""
        {prop}
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
    """


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")


@app.get("/style.css")
async def style_css(request):
    return await file("style.css", mime_type="text/css")
