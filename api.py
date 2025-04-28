import os
import functools
import json
import base64
from datetime import date
from itertools import chain
from types import CoroutineType
from sanic import Sanic, HTTPResponse, html, file, redirect
from nomnidate import NonOmniscientDate
import objects as O
from db import conn
from property_types import TYPES

PAGE_SIZE = 20
CORRECT_AUTH = os.environ["VERONIQUE_CREDS"]

app = Sanic("Veronique")

@app.on_request
async def auth(request):
    cookie = request.cookies.get("auth")
    if cookie == CORRECT_AUTH:
        return
    try:
        auth = request.headers["Authorization"]
        _, _, encoded = auth.partition(" ")
        if base64.b64decode(encoded).decode() == CORRECT_AUTH:
            response = redirect("/")
            response.add_cookie(
                "auth",
                CORRECT_AUTH,
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


def pagination(url, page_no, *, more_results=True, allow_negative=False):
    if page_no == 1 and not more_results:
        return ""
    q = "&" if "?" in url else "?"
    return f"""<br>
        <a
            role="button"
            class="prev"
            href="{url}{q}page={page_no - 1}"
            {"disabled" if page_no == 1 and not allow_negative else ""}
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
    recent_events = []
    page_no = int(request.args.get("page", 1))
    past_today = False
    reference_date = date.today()
    if page_no != 1:
        reference_date = reference_date.replace(month=((reference_date.month + (page_no - 1)) % 12) or 12)
    for fact in sorted(
        O.Fact.all_of_same_month(reference_date),
        key=lambda f: (
            (reference_date - NonOmniscientDate(f.obj.value)).days or 99
        ),
        reverse=True,
    ):
        difference = (reference_date - NonOmniscientDate(fact.obj.value)).days
        if difference == 0:
            past_today = True
        elif not past_today and difference < 0 and page_no == 1:
            recent_events.append('<hr class="date-today">')
            past_today = True
        recent_events.append(f"<p>{fact}</p>")
    if page_no == 1 and not past_today:
        recent_events.append('<hr class="date-today">')
    return f"""
        <button
            hx-get="/entities/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity</button>
        <h2>This month</h2>
        {"".join(recent_events)}
    """ + pagination(
        "/",
        page_no,
        more_results=True,
        allow_negative=True,
    )


@app.get("/network")
@page
async def network(request):
    all_categories = list(O.Category.all())
    if "categories" in request.args:
        ids = [int(part.removeprefix("cat")) for part in request.args["categories"]]
        categories = [O.Category(category_id) for category_id in ids]
    else:
        categories = all_categories
    all_properties = list(O.Property.all(data_type="entity"))
    if "properties" in request.args:
        ids = [int(part.removeprefix("prop")) for part in request.args["properties"]]
        properties = [O.Property(property_id) for property_id in ids]
    else:
        properties = all_properties
    entities = O.Entity.all(page_size=9999, categories=categories)
    elements = chain.from_iterable(
        e.graph_elements(categories, properties=properties)
        for e in entities
    )
    return f"""
    <form id="networkform">
    <fieldset class="grid">
    <details class="dropdown">
    <summary>Select Categories...</summary>
      <ul>
      {
          "".join(
              f'''<li><input
                  type="checkbox"
                  id="cat{cat.id}"
                  name="categories"
                  value="cat{cat.id}"
                  {"checked" if cat in categories else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="cat{cat.id}">{cat.name}</label></li>
              '''
              for cat in all_categories
          )
      }
      </ul>
    </details>
    <details class="dropdown">
    <summary>Select Properties...</summary>
      <ul>
      {
          "".join(
              f'''<li><input
                  type="checkbox"
                  id="prop{prop.id}"
                  name="properties"
                  value="prop{prop.id}"
                  {"checked" if prop in properties else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="prop{prop.id}">{prop.label}</label></li>
              '''
              for prop in all_properties
          )
      }
      </ul>
    </details>
    </fieldset>
    </form>
    <div id="cy"></div>
    <script>
        var cy = cytoscape({{
            container: document.getElementById("cy"),
            elements: [
            {",".join(json.dumps(element) for element in elements)}
            ],
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'label': 'data(label)',
                        'width': '5px',
                        'height': '5px',
                        'font-size': '5pt',
                    }}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'label': 'data(label)',
                        'font-size': '4pt',
                        'width': '1px',
                        'line-opacity': 0.2,
                    }}
                }},
            ],
        }});
        layout = cy.layout({{
            name: 'cose',
            initialTemp: 4000,
        }});
        layout.run();
    </script>
    """


@app.get("/categories")
@page
async def list_categories(request):
    categories = O.Category.all()
    return """
    <button
        hx-get="/category/new"
        hx-swap="outerHTML"
        class="button-new"
    >New category</button>
    """ + "<br>".join(str(category) for category in categories)


@app.get("/categories/new")
@fragment
async def new_category_form(request):
    return """
        <form
            hx-post="/categories/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="name" placeholder="name"></input>
            <button type="submit">»</button>
        </form>
    """


@app.post("/categories/new")
@fragment
async def new_category(request):
    form = D(request.form)
    name = form["name"]
    category = O.Category.new(name)
    return f"""
        <button
            hx-get="/categories/new"
            hx-swap="outerHTML"
            class="button-new"
        >New category</button>
        {category}
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
    more_results = False
    for i, entity in enumerate(O.Entity.all(
        order_by="category_id ASC, id DESC",
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )):
        if entity.category != previous_type:
            parts.append(f"<h3>{entity.category}</h3>")
            previous_type = entity.category
        elif i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{entity}")
    return "".join(parts) + pagination(
        "/entities",
        page_no,
        more_results=more_results,
    )


@app.get("/entities/autocomplete/<category_id>")
@fragment
async def autocomplete_entities(request, category_id: int):
    parts = []
    query = D(request.args).get("ac-query", "")
    if not query:
        return ""
    entities = O.Entity.search(
        q=query,
        page_size=5,
        category_id=category_id,
    )
    return "".join(
        f"{entity:ac-result:{category_id}}"
        for entity in entities
    )


@app.get("/entities/autocomplete/accept/<category_id>/<entity_id>")
@fragment
async def autocomplete_entities_accept(request, category_id: int, entity_id: int):
    entity = O.Entity(entity_id)
    return f"""
        <input
            name="ac-query"
            placeholder="Start typing..."
            hx-get="/entities/autocomplete/{category_id}"
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
    categories = O.Category.all()
    return f"""
        <form
            hx-post="/entities/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="name" placeholder="name"></input>
            <select name="category">
                <option selected disabled>--Category--</option>
                {"".join(f'<option value="{c.id}">{c.name}</option>' for c in categories)}
            </select>
            <button type="submit">»</button>
        </form>
    """


@app.post("/entities/new")
@fragment
async def new_entity(request):
    form = D(request.form)
    name = form["name"]
    entity = O.Entity.new(name, O.Entity(int(form["category"])))
    return f"""
        <button
            hx-get="/entities/new"
            hx-swap="outerHTML"
            class="button-new"
        >New entity</button>
        <br>
        <meta http-equiv="refresh" content="0; url=/entities/{entity.id}">
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

@app.get("/categories/<category_id>")
@page
async def view_category(request, category_id: int):
    page_no = int(request.args.get("page", 1))
    category = O.Category(category_id)
    entities = O.Entity.all(
        categories=[category],
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
        {category:heading}
        {"<br>".join(parts)}
        {pagination(
            f"/categories/{category_id}",
            page_no,
            more_results=more_results,
        )}
    """


@app.post("/categories/<category_id>/rename")
@fragment
async def rename_category(request, category_id: int):
    category = O.Category(category_id)
    name = D(request.form)["name"]
    if name:
        category.rename(name)
    return f"{category:heading}"


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
    props = O.Property.all(subject_category=entity.category, page_size=9999)
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
        value = O.Plain.from_form(fact.prop, form)
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
        value = O.Plain.from_form(prop, form)
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
    page_no = int(request.args.get("page", 1))
    parts = [
        """<button
            hx-get="/properties/new"
            hx-swap="outerHTML"
            class="button-new"
        >New property</button>"""
    ]
    more_results = False
    for i, prop in enumerate(O.Property.all(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,
    )):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{prop:full}")
    return "<br>".join(parts) + pagination(
        "/properties",
        page_no,
        more_results=more_results,
    )


@app.get("/properties/new")
@fragment
async def new_property_form(request):
    type_options = []
    for category in O.Category.all():
        type_options.append(f'<option value="{category.id}">{category}</option>')
    return f"""
        <form
            hx-post="/properties/new"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <select name="subject_category">
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
        subject_category=O.Category(int(form["subject_category"])),
        object_category=(
            O.Category(int(form["object_category"]))
            if "object_category" in form
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


@app.get("/queries")
@page
async def list_queries(request):
    page_no = int(request.args.get("page", 1))
    parts = [
        """<button
            hx-get="/queries/new"
            hx-swap="outerHTML"
            hx-target="#container"
            hx-select="#container"
            hx-push-url="true"
            class="button-new"
        >New query</button>"""
    ]
    more_results = False
    for i, query in enumerate(O.Query.all(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,
    )):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{query:full}")
    return "<br>".join(parts) + pagination(
        "/queries",
        page_no,
        more_results=more_results,
    )


@app.get("/queries/new")
@page
async def new_query_form(request):
    return f"""
        <form
            hx-post="/queries/new"
            hx-encoding="multipart/form-data"
        >
            <input name="label" placeholder="label"></input>
            <textarea
                hx-post="/queries/preview"
                hx-target="#preview"
                hx-trigger="keyup delay:500ms"
                name="sql"
            ></textarea>
            <button type="submit">»</button>
            <div id="preview"></div>
        </form>
    """


@app.get("/queries/<query_id>/edit")
@page
async def edit_query_form(request, query_id: int):
    query = O.Query(query_id)
    return f"""
        <form
            hx-put="/queries/{query_id}"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="label" placeholder="label" value="{query.label}"></input>
            <textarea
                hx-post="/queries/preview"
                hx-target="#preview"
                hx-trigger="keyup delay:500ms"
                name="sql"
            >{query.sql}</textarea>
            <button type="submit">»</button>
            <div id="preview"></div>
        </form>
    """


SPECIAL_COL_NAMES = {
    "short_fact": lambda value: f"{O.Fact(int(value)):short}",
    "short_facts": lambda value: ", ".join(
        f"{O.Fact(int(part)):short}" for part in value.split(",")
    ),
}
for singular, plural, model in (
    ("entity", "entities", O.Entity),
    ("fact", "facts", O.Fact),
    ("category", "categories", O.Category),
    ("property", "properties", O.Property),
):
    SPECIAL_COL_NAMES[singular] = model
    SPECIAL_COL_NAMES[plural] = lambda value, model=model: ", ".join(
        str(model(int(part)))
        for part in value.split(",")
    )


def display_query_result(result):
    if result:
        header = dict(result[0]).keys()
        parts = [
            "<table><thead><tr>",
            *(f"<td>{col}</td>" for col in header),
            "</tr></thead><tbody>",
        ]
        for row in result:
            parts.append("<tr>")
            for col in header:
                value = row[col]
                if col in SPECIAL_COL_NAMES:
                    value = SPECIAL_COL_NAMES[col](value)
                parts.append(f"<td>{value}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
        return "".join(parts)
    return ""


@app.post("/queries/preview")
@fragment
async def preview_query(request):
    form = D(request.form)
    res = None
    try:
        cur = conn.cursor()
        res = cur.execute(form["sql"]).fetchall()
    finally:
        conn.rollback()
    return display_query_result(res)


@app.post("/queries/new")
@fragment
async def new_query(request):
    form = D(request.form)
    query = O.Query.new(
        form["label"],
        form["sql"],
    )
    return f"""
        <meta http-equiv="refresh" content="0; url=/queries/{query.id}">
    """


@app.put("/queries/<query_id>")
@fragment
async def edit_query(request, query_id: int):
    query = O.Query(query_id)
    form = D(request.form)
    query.update(label=form["label"], sql=form["sql"])
    return f"""
        <meta http-equiv="refresh" content="0; url=/queries/{query_id}">
    """


@app.get("/queries/<query_id>")
@page
async def get_query(request, query_id: int):
    page_no = int(request.args.get("page", 1))
    query = O.Query(query_id)
    result = query.run(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )
    if len(result) > PAGE_SIZE:
        more_results = True
        result = result[:-1]
    else:
        more_results = False
    return f"{query:heading}{display_query_result(result)}" + pagination(
        f"/queries/{query_id}",
        page_no,
        more_results=more_results,
    )


@app.put("/entities/<entity_id>/avatar")
@fragment
async def put_avatar(request, entity_id: int):
    entity = O.Entity(entity_id)
    entity.upload_avatar(request.files["file"][0].body)
    return f"{entity:heading}"


@app.get("/entities/<entity_id>/avatar")
async def get_avatar(request, entity_id: int):
    return await file(f"avatars/{entity_id}.jpg", mime_type="image/jpeg")


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")


@app.get("/style.css")
async def style_css(request):
    return await file("style.css", mime_type="text/css")


@app.get("/mana-cost.css")
async def mana_cost_css(request):
    return await file("mana-cost.css", mime_type="text/css")


@app.get("/mana.svg")
async def mana_svg(request):
    return await file("mana.svg", mime_type="image/svg+xml")


@app.get("/pico.min.css")
async def pico_css(request):
    return await file("pico.min.css", mime_type="text/css")


@app.get("/cytoscape.min.js")
async def cytoscape_js(request):
    return await file("cytoscape.min.js", mime_type="text/javascript")


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("favicon.ico", mime_type="image/x-icon")


@app.get("/logo.svg")
async def logo_svg(request):
    return await file("logo.svg", mime_type="image/svg+xml")
