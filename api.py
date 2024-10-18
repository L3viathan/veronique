import os
import functools
import base64
from datetime import date
from types import CoroutineType
from sanic import Sanic, HTTPResponse, html, file, redirect
from nomnidate import NonOmniscientDate
import objects as O
from property_types import TYPES

PAGE_SIZE = 20

app = Sanic("Veronique")

@app.on_request
async def auth(request):
    correct_auth = os.environ["VERONIQUE_CREDS"]
    cookie = request.cookies.get("auth")
    if cookie == correct_auth:
        return
    try:
        auth = request.headers["Authorization"]
        _, _, encoded = auth.partition(" ")
        if base64.b64decode(encoded).decode() == correct_auth:
            response = redirect("/")
            response.add_cookie(
                "auth",
                correct_auth,
                secure=True,
                httponly=True,
                samesite="Strict",
                max_age=60*60*24*365,  # roughly one year
            )
            return response
        else:
            raise ValueError
    except (KeyError, AssertionError, ValueError):
        return HTTPResponse(
            body="401 Unauthorized",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Veronique access"'},
        )


def D(multival_dict):
    return {key: val[0] for key, val in multival_dict.items()}


def pagination(url, page_no, *, more_results=True):
    q = "&" if "?" in url else "?"
    return f"""<br>
        <a
            role="button"
            class="prev"
            href="{url}{q}page={page_no - 1}"
            {"disabled" if page_no == 1 else ""}
        >&lt;</a>
        <a
            class="next"
            role="button"
            href="{url}{q}page={page_no + 1}"
            {"disabled" if not more_results else ""}
        >&gt;</a>
    """


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
    return f"""
        <button
            hx-get="/entities/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity</button>
        <h2>This month</h2>
        {"".join(f"<p>{fact}</p>" for fact in sorted(
            O.Fact.all_of_same_month(),
            key=lambda f: (
                abs((date.today() - NonOmniscientDate(f.obj.value)).days)
            ),
        ))}
    """


@app.get("/entity-types")
@page
async def list_types(request):
    types = O.EntityType.all()
    return """
    <button
        hx-get="/entity-types/new"
        hx-swap="outerHTML"
        class="button-new"
    >New entity type</button>
    """ + "<br>".join(str(type_) for type_ in types)


@app.get("/entity-types/new")
@fragment
async def new_entity_type_form(request):
    return """
        <form
            hx-post="/entity-types/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
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
        <button
            hx-get="/entity-types/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity type</button>
        {entity_type}
        <br>
    """


@app.get("/entities")
@page
async def list_entities(request):
    page_no = int(request.args.get("page", 1))
    parts = [
        """<button
            hx-get="/entities/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity</button><br>"""
    ]
    previous_type = None
    n_results = 0
    more_results = False
    for i, entity in enumerate(O.Entity.all(
        order_by="entity_type_id ASC, id DESC",
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )):
        if entity.entity_type != previous_type:
            parts.append(f"<h3>{entity.entity_type}</h3>")
            previous_type = entity.entity_type
        elif i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{entity}")
            n_results += 1
    return "".join(parts) + pagination(
        "/entities",
        page_no,
        more_results=more_results,
    )


@app.get("/entities/autocomplete/<entity_type_id>")
@fragment
async def autocomplete_entities(request, entity_type_id: int):
    parts = []
    query = D(request.args).get("ac-query", "")
    if not query:
        return ""
    entities = O.Entity.search(
        q=query,
        page_size=5,
        entity_type_id=entity_type_id,
    )
    return "".join(
        f"{entity:ac-result:{entity_type_id}}"
        for entity in entities
    )


@app.get("/entities/autocomplete/accept/<entity_type_id>/<entity_id>")
@fragment
async def autocomplete_entities_accept(request, entity_type_id: int, entity_id: int):
    entity = O.Entity(entity_id)
    return f"""
        <input
            name="ac-query"
            placeholder="Start typing..."
            hx-get="/entities/autocomplete/{entity_type_id}"
            hx-target="next .ac-results"
            hx-swap="innerHTML"
            hx-trigger="input changed delay:200ms, search"
            value="{entity.name}"
        >
        <input type="hidden" name="value" value="{entity.id}"
        <div class="ac-results">
        </div>
    """


@app.get("/entities/new")
@fragment
async def new_entity_form(request):
    types = O.EntityType.all()
    return f"""
        <form
            hx-post="/entities/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="name" placeholder="name"></input>
            <select name="entity_type">
                <option selected disabled>--Entity Type--</option>
                {"".join(f'<option value="{et.id}">{et.name}</option>' for et in types)}
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
        <button
            hx-get="/entities/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity</button>
        <br>
        {entity:full}
    """


@app.get("/entities/search")
@page
async def search_entities(request):
    page_no = int(request.args.get("page", 1))
    query = D(request.args).get("q", "")
    entities = O.Entity.search(
        q=query,
        page_no=page_no - 1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )
    parts = []
    more_results = False
    for i, entity in enumerate(entities):
        if i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{entity:full}")
    return "".join(parts) + pagination(
        f"/entities/search?q={query}",
        page_no=page_no,
        more_results=more_results,
    )


@app.get("/entities/<entity_id>")
@page
async def view_entity(request, entity_id: int):
    entity = O.Entity(entity_id)
    return f"""
        <article>
            <header>{entity:heading}</header>
            <button
                hx-get="/facts/new/{entity_id}"
                hx-swap="outerHTML"
                class="button-new"
            >New fact</button>
        {"".join(f"<p>{fact:short}</p>" for fact in entity.facts)}
        </article>
        <h3>References</h3>
        {"".join(f"<p>{fact}</p>" for fact in entity.incoming_facts)}
    """

@app.get("/entity-types/<entity_type_id>")
@page
async def view_entity_type(request, entity_type_id: int):
    page_no = int(request.args.get("page", 1))
    entity_type = O.EntityType(entity_type_id)
    entities = O.Entity.all(
        entity_type=entity_type,
        page_no=page_no - 1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )
    parts = []
    more_results = False
    for i, entity in enumerate(entities):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{entity}")

    return f"""
        {entity_type:heading}
        {"<br>".join(parts)}
        {pagination(
            f"/entity-types/{entity_type_id}",
            page_no,
            more_results=more_results,
        )}
    """


@app.post("/entity-types/<entity_type_id>/rename")
@fragment
async def rename_entity_type(request, entity_type_id: int):
    entity_type = O.EntityType(entity_type_id)
    name = D(request.form)["name"]
    if name:
        entity_type.rename(name)
    return f"{entity_type:heading}"


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
        <form
            hx-post="/facts/new/{entity_id}"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <select
                name="property"
                hx-get="/facts/new/{entity_id}/property"
                hx-target="#valueinput"
                hx-swap="innerHTML"
            >
                <option selected disabled>--Property--</option>
                {"".join(
                    f'''<option
                            value="{prop.id}"
                        >{prop.label} ({prop.data_type})</option>'''
                    for prop in props
                )}
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/facts/new/<entity_id>/property")
@fragment
async def new_fact_form_property_input(request, entity_id: int):
    prop = O.Property(int(D(request.args)["property"]))
    entity = O.Entity(entity_id)
    return f"""
        {prop.data_type.input_html(entity, prop)}
        <button type="submit">»</button>
        """


@app.get("/facts/<fact_id>/edit")
@fragment
async def edit_fact_form(request, fact_id: int):
    fact = O.Fact(fact_id)
    return f"""
        <form
            hx-post="/facts/{fact_id}/edit"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            {fact.prop.data_type.input_html(fact.subj, fact.prop, value=fact.obj)}
            <button type="submit">»</button>
        </form>
        """


@app.get("/facts/<fact_id>/change-valid-from")
@fragment
async def change_valid_from_form(request, fact_id: int):
    fact = O.Fact(fact_id)
    value = f' value="{fact.valid_from:%Y-%m-%d}"' if fact.valid_from else ""
    return f"""
        <form
            hx-post="/facts/{fact_id}/change-valid-from"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="date" type="date"{value}></input>
            <button type="submit">»</button>
        </form>
    """


@app.post("/facts/<fact_id>/change-valid-from")
@fragment
async def change_valid_from(request, fact_id: int):
    fact = O.Fact(fact_id)
    form = D(request.form)
    fact.set_validity(valid_from=form["date"])
    return f"{fact:valid_from}"


@app.get("/facts/<fact_id>/change-valid-until")
@fragment
async def change_valid_until_form(request, fact_id: int):
    fact = O.Fact(fact_id)
    value = f' value="{fact.valid_until:%Y-%m-%d}"' if fact.valid_until else ""
    return f"""
        <form
            hx-post="/facts/{fact_id}/change-valid-until"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="date" type="date"{value}></input>
            <button type="submit">»</button>
        </form>
    """


@app.post("/facts/<fact_id>/change-valid-until")
@fragment
async def change_valid_until(request, fact_id: int):
    fact = O.Fact(fact_id)
    form = D(request.form)
    fact.set_validity(valid_until=form["date"])
    return f"{fact:valid_until}"


@app.delete("/facts/<fact_id>")
@fragment
async def delete_fact(request, fact_id: int):
    fact = O.Fact(fact_id)
    fact.delete()
    return ""


@app.post("/facts/<fact_id>/edit")
@fragment
async def edit_fact(request, fact_id: int):
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
    fact = O.Fact(fact_id)
    value = form.get("value")
    if fact.prop.data_type.name == "entity":
        value = O.Entity(int(value))
    else:
        value = O.Plain(value, fact.prop)
        value.fact = fact
    fact.set_value(value)
    return f"{fact.obj}"


@app.post("/facts/new/<entity_id>")
@fragment
async def new_fact(request, entity_id: int):
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
    prop = O.Property(int(form["property"]))
    value = form.get("value")
    if prop.data_type.name == "entity":
        value = O.Entity(int(value))
    else:
        value = O.Plain(value, prop)
    fact = O.Fact.new(O.Entity(entity_id), prop, value)
    if prop.data_type.name != "entity":
        value.fact = fact
    return f"""
        <button
            hx-get="/facts/new/{entity_id}"
            hx-swap="outerHTML"
            class="button-new"
        >New fact</button>
        <p>{fact:short}</p>
    """


@app.get("/properties")
@page
async def list_properties(request):
    parts = [
        """<button
            hx-get="/properties/new"
            hx-swap="outerHTML"
            class="button-new"
        >New property</button>"""
    ]
    parts.extend(f"{prop:full}" for prop in O.Property.all())
    return "<br>".join(parts)


@app.get("/properties/new")
@fragment
async def new_property_form(request):
    type_options = []
    for entity_type in O.EntityType.all():
        type_options.append(f'<option value="{entity_type.id}">{entity_type}</option>')
    return f"""
        <form
            hx-post="/properties/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <select name="subject_type">
                <option selected disabled>--Subject--</option>
                {"".join(type_options)}
            </select>
            <input name="label" placeholder="label"></input>
            <select
                name="data_type"
                hx-get="/properties/new/steps"
                hx-target="#steps"
                hx-swap="innerHTML"
            >
                <option selected disabled>--Type--</option>
                {"".join(
                    f'''<option value="{data_type}">{data_type}</option>'''
                    for data_type in TYPES
                )}
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
        object_type=(
            O.EntityType(int(form["object_type"]))
            if "object_type" in form
            else None
        ),
        extra_data=data_type.encode_extra_data(form),
    )
    return f"""
        <button
            hx-get="/properties/new"
            hx-swap="outerHTML"
            class="button-new"
        >New property</button>
        {prop:full}
    """


@app.get("/facts/<fact_id>")
@page
async def view_fact(request, fact_id: int):
    fact = O.Fact(fact_id)
    return f"""
        {fact:heading}
        created: {fact.created_at}<br>
        updated: {fact.updated_at or "(null)"}<br>
        valid_from: {fact:valid_from}<br>
        valid_until: {fact:valid_until}<br>
    """


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")


@app.get("/style.css")
async def style_css(request):
    return await file("style.css", mime_type="text/css")


@app.get("/pico.min.css")
async def pico_css(request):
    return await file("pico.min.css", mime_type="text/css")


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("favicon.ico", mime_type="image/x-icon")


@app.get("/logo.svg")
async def logo_svg(request):
    return await file("logo.svg", mime_type="image/svg+xml")
