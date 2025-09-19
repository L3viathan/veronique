import os
import functools
import json
import base64
import sqlite3
from datetime import date
from types import CoroutineType
from sanic import Sanic, HTTPResponse, html, file, redirect
from nomnidate import NonOmniscientDate
import objects as O
from db import conn, LABEL, IS_A, ROOT, AVATAR, make_search_key
from data_types import TYPES

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
        if isinstance(ret, str):
            title = "Véronique"
        else:
            title, ret = ret
            title = f"{title} — Véronique"
        return html(TEMPLATE(title, ret))
    return wrapper


def coalesce(*values):
    for val in values:
        if val is not None:
            return val
    return values[-1]


@app.get("/")
@page
async def index(request):
    recent_events = []
    page_no = int(request.args.get("page", 1))
    past_today = False
    reference_date = date.today()
    if page_no != 1:
        reference_date = reference_date.replace(
            day=1,
            month=((reference_date.month + (page_no - 1)) % 12) or 12,
        )
    for claim in sorted(
        O.Claim.all_of_same_month(reference_date),
        key=lambda c: (
            # unspecified dates are always before everything else
            coalesce((reference_date - NonOmniscientDate(c.object.value)).days, 99)
        ),
        reverse=True,
    ):
        difference = coalesce(
            (reference_date - NonOmniscientDate(claim.object.value)).days,
            99,
        )
        if difference == 0:
            past_today = True
        elif not past_today and (difference or 0) < 0 and page_no == 1:
            recent_events.append('<hr class="date-today">')
            past_today = True
        recent_events.append(f"<p>{claim:link}</p>")
    if page_no == 1 and not past_today:
        recent_events.append('<hr class="date-today">')
    heading = {1: "This month", 0: "Last month", 2: "Next month"}.get(page_no, f"{reference_date:%B}")
    return f"""
        <article><header>
        <h2>{heading}</h2>
        </header>
        {"".join(recent_events)}
    """ + pagination(
        "/",
        page_no,
        more_results=True,
        allow_negative=True,
    ) + "</article>"


@app.get("/network")
@page
async def network(request):
    all_categories = list(O.Claim.all_categories(page_size=9999))
    if "categories" in request.args:
        ids = [int(part.removeprefix("cat")) for part in request.args["categories"]]
        categories = {O.Claim(category_id) for category_id in ids}
    else:
        categories = None
    all_verbs = list(O.Verb.all(data_type="%directed_link"))
    if "verbs" in request.args:
        ids = [int(part.removeprefix("verb")) for part in request.args["verbs"]]
        verbs = [O.Verb(verb_id) for verb_id in ids]
    else:
        verbs = all_verbs
    claims = (
        c
        for c in O.Claim.all_labelled(page_size=9999)
        if categories is None or ({cat.object for cat in c.get_data().get(IS_A, set())} & categories)
    )
    node_ids = set()
    elements, all_edges = [], []
    for c in claims:
        node, edges = c.graph_elements(verbs=verbs)
        elements.append(node)
        node_ids.add(node["data"]["id"])
        all_edges.extend(edges)
    for edge in all_edges:
        if edge["data"]["source"] in node_ids and edge["data"]["target"] in node_ids:
            elements.append(edge)

    return "Network", f"""
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
                  {"checked" if categories is None or cat in categories else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="cat{cat.id}">{cat:label}</label></li>
              '''
              for cat in all_categories
          )
      }
      </ul>
    </details>
    <details class="dropdown">
    <summary>Select Verbs...</summary>
      <ul>
      {
          "".join(
              f'''<li><input
                  type="checkbox"
                  id="verb{verb.id}"
                  name="verbs"
                  value="verb{verb.id}"
                  {"checked" if verb in verbs else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="verb{verb.id}">{verb.label}</label></li>
              '''
              for verb in all_verbs
              if verb.id not in (IS_A, ROOT)
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


@app.get("/claims/autocomplete")
@fragment
async def autocomplete_claims(request):
    query = D(request.args).get("ac-query", "")
    if not query:
        return ""
    claims = O.Claim.search(
        q=query,
        page_size=5,
    )
    return "".join(
        f"{claim:ac-result}"
        for claim in claims
    )


@app.get("/claims/autocomplete/accept/<claim_id>")
@fragment
async def autocomplete_claims_accept(request, claim_id: int):
    claim = O.Claim(claim_id)
    return f"""
        <input
            name="ac-query"
            placeholder="Start typing..."
            hx-get="/claims/autocomplete"
            hx-target="next .ac-results"
            hx-swap="innerHTML"
            hx-trigger="input changed delay:200ms, search"
            value="{claim:label}"
        >
        <input type="hidden" name="value" value="{claim.id}"
        <div class="ac-results">
        </div>
    """


@app.get("/claims/new-root")
@page
async def new_root_claim_form(request):
    categories = O.Claim.all_categories()
    return "New root", f"""
    <article>
    <heading><h2>New root claim</h2></heading>
        <form action="/claims/new-root" method="POST">
            <input name="name" placeholder="name"></input>
            <select
                name="category"
            >
                <option value="">(None)</option>
                {"".join(
                    f'''<option
                            value="{cat.id}"
                            {'selected="selected"' if i == 0 else ""}
                        >{cat:label}</option>'''
                    for i, cat in enumerate(categories)
                )}
            </select>
            <button type="submit">»</button>
        </form>
    </article>
    """


@app.post("/claims/new-root")
async def new_root_claim(request):
    form = D(request.form)
    name = form["name"]
    claim = O.Claim.new_root(name)
    if form.get("category"):
        cat = O.Claim(int(form["category"]))
        O.Claim.new(claim, O.Verb(IS_A), cat)
    return redirect(f"/claims/{claim.id}")


@app.get("/claims/new/<claim_id>/<direction:incoming|outgoing>")
@fragment
async def new_claim_form(request, claim_id: int, direction: str):
    verbs = O.Verb.all(page_size=9999, data_type="directed_link" if direction == "incoming" else None)
    return f"""
        <form
            action="/claims/new/{claim_id}/{direction}"
            method="POST"
            enctype="multipart/form-data"
        >
            <select
                name="verb"
                hx-get="/claims/new/verb"
                hx-target="#valueinput"
                hx-swap="innerHTML"
            >
                <option selected disabled>--Verb--</option>
                {"".join(
                    f'''<option
                            value="{verb.id}"
                        >{verb.label} ({verb.data_type})</option>'''
                    for verb in verbs
                    if verb.id != ROOT
                )}
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/claims/new/verb")
@fragment
async def new_claim_form_verb_input(request):
    verb = O.Verb(int(D(request.args)["verb"]))
    return f"""
        {verb.data_type.input_html()}
        <button type="submit">»</button>
        """


@app.post("/claims/new/<claim_id>/<direction:incoming|outgoing>")
async def new_claim(request, claim_id: int, direction: str):
    claim = O.Claim(claim_id)
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
    verb = O.Verb(int(form["verb"]))
    value = form.get("value")
    if verb.data_type.name.endswith("directed_link"):
        value = O.Claim(int(value))
    else:
        value = O.Plain.from_form(verb, form)
    if direction == "incoming":
        O.Claim.new(value, verb, claim)
    else:
        O.Claim.new(claim, verb, value)
    return redirect(f"/claims/{claim_id}")


@app.get("/search")
@page
async def search(request):
    page_no = int(request.args.get("page", 1))
    query = D(request.args).get("q", "")
    cur = conn.cursor()
    hits = cur.execute(
        """
            SELECT table_name, id
            FROM search_index WHERE value LIKE '%' || ? || '%'
            LIMIT ?
            OFFSET ?
        """,
        (make_search_key(query), PAGE_SIZE + 1, PAGE_SIZE * (page_no - 1))
    ).fetchall()
    parts = []
    more_results = False
    for i, hit in enumerate(hits):
        if i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            if hit["table_name"] == "claims":
                parts.append(f"{O.Claim(hit['id']):link}")
            elif hit["table_name"] == "queries":
                parts.append(f"{O.Query(hit['id']):link}")
            elif hit["table_name"] == "verbs":
                parts.append(f"{O.Verb(hit['id']):link}")
            else:
                parts.append("TODO: implement for", hit["table_name"])
    return "".join(parts) + pagination(
        f"/search?q={query}",
        page_no=page_no,
        more_results=more_results,
    )


@app.get("/claims/<claim_id>/edit")
@fragment
async def edit_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    return f"""
        <form
            action="/claims/{claim_id}/edit"
            method="POST"
        >
            {claim.verb.data_type.input_html(value=claim.object)}
            <button type="submit">»</button>
        </form>
        """


@app.delete("/claims/<claim_id>")
@fragment
async def delete_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    claim.delete()
    return """
        <meta http-equiv="refresh" content="0; url=/">
    """


@app.post("/claims/<claim_id>/edit")
async def edit_claim(request, claim_id: int):
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
    claim = O.Claim(claim_id)
    value = form.get("value")
    if claim.verb.data_type.name.endswith("directed_link"):
        # no longer allowed
        raise RuntimeError("Can't edit links; delete it and make a new one")
    else:
        value = O.Plain.from_form(claim.verb, form)
    claim.set_value(value)
    return redirect(f"/claims/{claim_id}")


@app.get("/verbs")
@page
async def list_verbs(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, verb in enumerate(O.Verb.all(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,
    )):
        if i == PAGE_SIZE:
            more_results = True
        elif verb.id not in (ROOT, LABEL):
            parts.append(f"{verb:full}")
    return "Verbs", "<br>".join(parts) + pagination(
        "/verbs",
        page_no,
        more_results=more_results,
    )


@app.get("/verbs/new")
@page
async def new_verb_form(request):
    return "New verb", f"""
        <form
            action="/verbs/new"
            method="POST"
        >
            <input name="label" placeholder="label"></input>
            <select
                name="data_type"
                hx-get="/verbs/new/steps"
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


@app.get("/verbs/new/steps")
@fragment
async def new_verb_form_steps(request):
    args = D(request.args)
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">»</button>'


@app.post("/verbs/new")
async def new_verb(request):
    form = D(request.form)
    data_type = TYPES[form["data_type"]]
    verb = O.Verb.new(
        form["label"],
        data_type=data_type,
    )
    return redirect(f"/verbs/{verb.id}")


@app.get("/queries")
@page
async def list_queries(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, query in enumerate(O.Query.all(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,
    )):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{query:full}")
    return "Queries", "<br>".join(parts) + pagination(
        "/queries",
        page_no,
        more_results=more_results,
    )


def _queries_textarea(value=None):
    return f"""
        <div>
        <textarea
            id="editing"
            name="sql"
            spellcheck="false"
            oninput="update(this.value); sync_scroll(this);"
            onscroll="sync_scroll(this);"
            onload="setTimeout(function(){{update(this.value); sync_scroll(this);}}, 100)"
        >{value or ""}</textarea>
        <pre id="highlighting" aria-hidden="true"><code
                class="language-sql"
                id="highlighting-content"
            >{value or ""}</code>
        </pre>
        </div>
    """


@app.get("/queries/new")
@page
async def new_query_form(request):
    return "New query", f"""
        <form
            hx-post="/queries/new"
            hx-encoding="multipart/form-data"
        >
            <input name="label" placeholder="label"></input>
            {_queries_textarea()}
            <div role="group">
            <button
                class="secondary"
                hx-post="/queries/preview"
                hx-target="#preview"
                hx-include="#editing"
                hx-swap="innerHTML"
            >Preview</button>
            <button type="submit">»</button>
            </div>
            <div id="preview"></div>
        </form>
    """


@app.get("/queries/<query_id>/edit")
@page
async def edit_query_form(request, query_id: int):
    query = O.Query(query_id)
    return f"Edit {query.label!r}", f"""
        <form
            hx-put="/queries/{query_id}"
            hx-swap="outerHTML"
            hx-encoding="multipart/form-data"
        >
            <input name="label" placeholder="label" value="{query.label}"></input>
            {_queries_textarea(query.sql)}
            <div role="group">
            <button
                class="secondary"
                hx-post="/queries/preview"
                hx-target="#preview"
                hx-include="#editing"
                hx-swap="innerHTML"
            >Preview</button>
            <button type="submit">»</button>
            </div>
            <div id="preview"></div>
        </form>
    """


SPECIAL_COL_NAMES = {}
for singular, plural, model in (
    ("c", "cs", O.Claim),
    ("v", "vs", O.Verb),
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
                if col.endswith(tuple(SPECIAL_COL_NAMES)):
                    _, __, ending = col.rpartition("_")
                    value = SPECIAL_COL_NAMES[ending](value)
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
        res = cur.execute(form["sql"] + " LIMIT 10").fetchall()
    except (sqlite3.Warning, sqlite3.OperationalError) as e:
        return f"""<article class="error"><strong>Error:</strong> {e.args[0]}</article>"""
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
async def view_query(request, query_id: int):
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
    return query.label, f"""
        <article><header>
        {query:heading}</header>{display_query_result(result)}
    """ + pagination(
        f"/queries/{query_id}",
        page_no,
        more_results=more_results,
    ) + "</article>"


@app.get("/claims")
@page
async def list_labelled_claims(request):
    page_no = int(request.args.get("page", 1))
    parts = [
    ]
    more_results = False
    for i, claim in enumerate(O.Claim.all_labelled(
        order_by="id DESC",
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )):
        if i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{claim:link}")
    return "Claims", "".join(parts) + pagination(
        "/claims",
        page_no,
        more_results=more_results,
    )


@app.get("/claims/<claim_id>")
@page
async def view_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    incoming_mentions = list(claim.incoming_mentions())
    return f"{claim:label}", f"""
        <article>
            <header>{claim:heading}{claim:avatar}</header>
            <div id="edit-area"></div>
            <table class="claims"><tr><td>
        <div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/incoming" class="new-item-placeholder">+</div>
        {"".join(f"<p>{c:sv}</p>" for c in claim.incoming_claims())}
        </td><td>
        <div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/outgoing" class="new-item-placeholder">+</div>
        {"".join(f"<p>{c:vo:{claim_id}}</p>" for c in claim.outgoing_claims() if c.verb.id not in (LABEL, IS_A, AVATAR))}
        </td></tr></table>
        {"<hr><h3>Mentions</h3>" + "".join(f"<p>{c:svo}</p>" for c in incoming_mentions) if incoming_mentions else ""}
        </article>
    """


@app.get("/verbs/<verb_id>")
@page
async def view_verb(request, verb_id: int):
    page_no = int(request.args.get("page", 1))
    verb = O.Verb(verb_id)
    parts = [f"<article><heading>{verb:heading}</heading>"]
    more_results = False
    for i, claim in enumerate(verb.claims(
        page_no=page_no-1,
        page_size=PAGE_SIZE + 1,  # so we know if there would be more results
    )):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"<p>{claim:svo}</p>")
    parts.append("</article>")
    return verb.label, "".join(parts) + pagination(
        f"/verbs/{verb_id}",
        page_no,
        more_results=more_results,
    )


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


@app.get("/prism.css")
async def prism_css(request):
    return await file("prism.css", mime_type="text/css")


@app.get("/pico.min.css")
async def pico_css(request):
    return await file("pico.min.css", mime_type="text/css")


@app.get("/prism.js")
async def prism_js(request):
    return await file("prism.js", mime_type="text/javascript")


@app.get("/cytoscape.min.js")
async def cytoscape_js(request):
    return await file("cytoscape.min.js", mime_type="text/javascript")


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("favicon.ico", mime_type="image/x-icon")


@app.get("/logo.svg")
async def logo_svg(request):
    return await file("logo.svg", mime_type="image/svg+xml")
