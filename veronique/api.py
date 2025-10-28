import functools
import json
import re
import base64
import sqlite3
from secrets import token_urlsafe
from datetime import date, datetime, timedelta
from types import CoroutineType
from sanic import Sanic, HTTPResponse, html, file, redirect

import veronique.objects as O
import veronique.security as security
from veronique.context import context
from veronique.nomnidate import NonOmniscientDate
from veronique.db import conn, LABEL, IS_A, ROOT, AVATAR, COMMENT, make_search_key
from veronique.data_types import TYPES

PAGE_SIZE = 20

app = Sanic("Veronique")

with open("data/template.html") as f:
    TEMPLATE = f.read().format

with open("data/login.html") as f:
    LOGIN = f.read()


def _error(msg):
    return f"""
    <aside id="errors"><strong>Error:</strong> {msg} <span class="dismiss" hx-get="about:blank" hx-on:click="document.getElementById('errors').remove()">×</span></aside>
    """


def _notice(msg):
    return f"""
    <aside id="notices"><strong>Info:</strong> {msg} <span class="dismiss" hx-get="about:blank" hx-on:click="document.getElementById('notices').remove()">×</span></aside>
    """


@app.on_request
async def auth(request):
    """Ensure that each request is either authenticated or going to an explicitly allowed resource."""
    if request.name and (
        request.name in ("Veronique.login", "Veronique.do_login")
        or request.name.endswith(("_css", "_js", "_svg"))
    ):
        # allow unauthenticated access to login page
        context.user = None
        context.payload = None
        return
    unauthorized = redirect("/login")
    if payload := security.unsign(request.cookies.get("session")):
        if (datetime.now() - datetime.fromisoformat(payload["t"])) > timedelta(days=30):
            return unauthorized
        user = O.User(payload["u"])
        if user.generation > payload.get("g", 0):
            # this is to support proper logouts, see logout()
            return unauthorized
        context.user = user
        context.payload = payload
        return
    return unauthorized


@app.on_response
async def refresh_session(request, response):
    """If authenticated requests have overly old payloads, refresh them."""
    if not (payload := context.payload):
        return
    if (datetime.now() - datetime.fromisoformat(payload["t"])) > timedelta(days=7):
        response.add_cookie(
            "session",
            security.sign(context.user.payload),
            secure=True,
            httponly=True,
            samesite="Strict",
            # roughly one month (afterwards it will anyways be invalid):
            max_age=60 * 60 * 24 * 31,
        )


def admin_only(fn):
    """Mark an endpoint to be only accessible by admins. Must be above @page."""

    @functools.wraps(fn)
    async def wrapper(request, *args, **kwargs):
        if not context.user.is_admin:
            return HTTPResponse(
                body="403 Forbidden",
                status=403,
            )
        ret = fn(request, *args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        return ret

    return wrapper


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


def fragment(fn):
    """Mark an endpoint as returning HTML, but not a full page."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ret = fn(*args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, HTTPResponse):
            return ret
        return html(ret)

    return wrapper


def page(fn):
    """Mark an endpoint as returning a full standalone page."""

    @functools.wraps(fn)
    async def wrapper(request, *args, **kwargs):
        ret = fn(request, *args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, str):
            title = "Véronique"
        elif isinstance(ret, HTTPResponse):
            return ret
        else:
            title, ret = ret
            title = f"{title} — Véronique"

        gotos = []
        for page_name, restricted in [
            ("claims", False),
            ("verbs", False),
            ("network", False),
            ("queries", False),
            ("users", True),
        ]:
            if restricted and not context.user.is_admin:
                gotos.append(f'<li><a href="#" disabled>{page_name.title()}</a></li>')
            else:
                gotos.append(f'<li><a href="/{page_name}">{page_name.title()}</a></li>')
        if context.user.is_admin:
            news = """
            <li>
                <details class="dropdown clean">
                    <summary id="add-button">+
                    </summary>
                    <ul>
                        <li><a href="/claims/new-root">Root claim</a></li>
                        <li><a href="/verbs/new">Verb</a></li>
                        <li><a href="/queries/new">Query</a></li>
                        <li><a href="/users/new">User</a></li>
                    </ul>
                </details>
            </li>
            """
        elif context.user.can("write", "verb", ROOT):
            news = """
            <li>
                <a href="/claims/new-root" id="add-button">+</a>
            </li>
            """
        else:
            news = ""
        user = f"""
        <li>
            <details class="dropdown">
                <summary>{context.user.name}</summary>
                <ul dir="rtl"><li><a href="/logout">Logout</a></li></ul>
            </details>
        </li>
        """
        return html(
            TEMPLATE(
                title=title,
                content=ret,
                gotos="".join(gotos),
                news=news,
                user=user,
                errors=_error(request.args["err"][0]) if "err" in request.args else "",
            )
        )

    return wrapper


def coalesce(*values):
    """Like SQL's COALESCE() (where NULL = None)."""
    for val in values:
        if val is not None:
            return val
    return values[-1]


@app.get("/logout")
async def logout(request):
    # In order to support global logout despite having no server-side sessions,
    # users have a "generation", which needs to be the same as the generation
    # of the token payload. On logout, we increment that generation, such that
    # all previously issued tokens are invalidated.
    context.user.increment_generation()
    response = redirect("/")
    response.delete_cookie("session")
    return response


@app.get("/login")
async def login(request):
    return html(LOGIN)


@app.post("/login")
async def do_login(request):
    form = D(request.form)
    username = form["username"]
    password = form["password"]
    if not re.match("^[a-z]+$", username):
        # this could probably be removed, but.. yeah let's not.
        return redirect("/login")
    try:
        user = O.User.by_name(username)
    except ValueError:
        return redirect("/login")
    if security.is_correct(password, user.hash, user.salt):
        response = redirect("/")
        response.add_cookie(
            "session",
            security.sign(user.payload),
            secure=True,
            httponly=True,
            samesite="Strict",
            # roughly one month (afterwards it will anyways be invalid):
            max_age=60 * 60 * 24 * 31,
        )
        return response
    return redirect("/login")


@app.get("/")
@page
async def index(request):
    recent_events = []
    page_no = int(request.args.get("page", 1))
    past_today = False
    days_back = 3
    days_ahead = 7
    reference_date = date.today()
    if page_no != 1:
        reference_date += timedelta(days=(days_back+days_ahead+1)*(page_no-1))
    for claim in sorted(
        O.Claim.all_near_today(reference_date, days_back=days_back, days_ahead=days_ahead),
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
        recent_events.append(f'<span class="row">{claim:link}</span>')
    if page_no == 1 and not past_today:
        recent_events.append('<hr class="date-today">')
    heading = f"Events near {'today' if page_no == 1 else f'{reference_date:%m-%d}'}"
    return f"""
        <article><header>
        <h2>{heading}</h2>
        </header>
        {"".join(recent_events)}
        {pagination("/",
            page_no,
            more_results=True,
            allow_negative=True,
        )}
        </article>
        {_notice('There are <a href="/comments">unresolved comments</a>') if context.user.is_admin and list(O.Claim.all_comments()) else ""}
    """


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
        if categories is None
        or ({cat.object for cat in c.get_data().get(IS_A, set())} & categories)
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
    args = D(request.args)
    query = args.get("ac-query", "")
    connect = args.get("connect", None)
    if not query:
        return ""
    claims = O.Claim.search(
        q=query,
        page_size=5,
    )
    return f"""
    {"".join(f"{claim:ac-result}" for claim in claims if context.user.can("read", "verb", claim.verb.id))}
    {f'''<a class="clickable" href="/claims/new-root?connect={connect}&name={query}">
        <em>Create</em> {query} <em> claim...</em>
    </a>''' if connect is not None else ''}
    """


@app.get("/claims/autocomplete/accept/<claim_id>")
@fragment
async def autocomplete_claims_accept(request, claim_id: int):
    claim = O.Claim(claim_id)
    return f"""
        <input
            name="ac-query"
            placeholder="Start typing..."
            hx-get="/claims/autocomplete?claim={claim_id}"
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
    if not context.user.can("write", "verb", ROOT):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    categories = O.Claim.all_categories()
    args = D(request.args)
    connect_info = ""
    if connect := args.get("connect"):
        conn_claim_id, conn_dir, conn_verb_id = connect.split(":")
        if context.user.can("write", "verb", int(conn_verb_id)):
            conn_verb = O.Verb(int(conn_verb_id))
            conn_claim = O.Claim(int(conn_claim_id))
            connect_info = f"""
            <p>After creation, an {conn_dir} {conn_verb:link} link will be made to {conn_claim:link}.</p>
            <input type="hidden" name="connect" value="{connect}">
            """
    name = args.get("name", "")
    return "New root", f"""
    <article>
    <header><h2>New root claim</h2></header>
        <form action="/claims/new-root" method="POST">
            <input name="name" placeholder="name" value="{name}"></input>
            <select
                name="category"
            >
                <option value="">(None)</option>
                {
            "".join(
                f'''<option
                            value="{cat.id}"
                            {'selected="selected"' if i == 0 else ""}
                        >{cat:label}</option>'''
                for i, cat in enumerate(categories)
            )
        }
            </select>
            {connect_info}
            <button type="submit">»</button>
        </form>
    </article>
    """


@app.post("/claims/new-root")
async def new_root_claim(request):
    form = D(request.form)
    name = form["name"]
    if not all((context.user.can("write", "verb", v) for v in (ROOT, LABEL))):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    claim = O.Claim.new_root(name)
    if form.get("category") and context.user.can("write", "verb", IS_A):
        cat = O.Claim(int(form["category"]))
        O.Claim.new(claim, O.Verb(IS_A), cat)
    if connect := form.get("connect"):
        conn_claim_id, conn_dir, conn_verb_id = connect.split(":")
        if context.user.can("write", "verb", int(conn_verb_id)):
            conn_verb = O.Verb(int(conn_verb_id))
            conn_claim = O.Claim(int(conn_claim_id))
            if conn_dir == "incoming":
                O.Claim.new(claim, conn_verb, conn_claim)
            else:
                O.Claim.new(conn_claim, conn_verb, claim)
            # We came from the conn_claim, so we want to go back there.
            return redirect(f"/claims/{conn_claim.id}")
        # If we couldn't make the link, we want to go to the new root instead.
    return redirect(f"/claims/{claim.id}")


@app.get("/claims/new/<claim_id>/<direction:incoming|outgoing>")
@fragment
async def new_claim_form(request, claim_id: int, direction: str):
    verbs = O.Verb.all(
        page_size=9999, data_type="directed_link" if direction == "incoming" else None, only_writable=True
    )
    return f"""
        <form
            action="/claims/new/{claim_id}/{direction}"
            method="POST"
            enctype="multipart/form-data"
        >
            <select
                name="verb"
                hx-get="/claims/new/verb?claim_id={claim_id}&direction={direction}"
                hx-target="#valueinput"
                hx-swap="innerHTML"
            >
                <option selected disabled>--Verb--</option>
                {
                    "".join(
                        f'''<option
                                        value="{verb.id}"
                                    >{verb.label} ({verb.data_type})</option>'''
                        for verb in verbs
                        if verb.id != ROOT
                    )
                }
            </select>
            <span id="valueinput"></span>
        </form>
    """


@app.get("/claims/new/verb")
@fragment
async def new_claim_form_verb_input(request):
    args = D(request.args)
    if not context.user.can("write", "verb", int(args["verb"])):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verb = O.Verb(int(args["verb"]))
    return f"""
        {verb.data_type.input_html(claim_id=args.get("claim_id"), direction=args.get("direction"), verb_id=verb.id)}
        <button type="submit">»</button>
        """


@app.post("/claims/new/<claim_id>/<direction:incoming|outgoing>")
async def new_claim(request, claim_id: int, direction: str):
    claim = O.Claim(claim_id)
    form = D(request.form)
    if not (
        context.user.can("read", "verb", claim.verb.id)
        and context.user.can("write", "verb", int(form["verb"]))
    ):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
    verb = O.Verb(int(form["verb"]))
    value = form.get("value")
    if verb.data_type.name.endswith("directed_link"):
        value = O.Claim(int(value))
        if not context.user.can("read", "verb", value.verb.id):
            return HTTPResponse(
                body="403 Forbidden",
                status=403,
            )
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
        (make_search_key(query), PAGE_SIZE + 1, PAGE_SIZE * (page_no - 1)),
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
                if context.user.can("read", "query", hit["id"]):
                    parts.append(f"{O.Query(hit['id']):link}")
            elif hit["table_name"] == "verbs":
                if context.user.can("read", "verb", hit["id"]):
                    parts.append(f"{O.Verb(hit['id']):link}")
            else:
                parts.append(f"TODO: implement for {hit['table_name']}")
    return "".join(parts) + pagination(
        f"/search?q={query}",
        page_no=page_no,
        more_results=more_results,
    )


@app.get("/claims/<claim_id>/edit")
@fragment
async def edit_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    return f"""
        <form
            action="/claims/{claim_id}/edit"
            method="POST"
        >
            {claim.verb.data_type.input_html(value=claim.object)}
            <button type="submit">»</button>
        </form>
        """


@app.get("/claims/<claim_id>/move")
@fragment
async def move_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    return f"""
        <form
            action="/claims/{claim_id}/move"
            method="POST"
        >
            {TYPES["directed_link"].input_html(value=claim.object, allow_connect=False)}
            <button type="submit">»</button>
        </form>
        """


@app.delete("/claims/<claim_id>")
@fragment
async def delete_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
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
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    value = form.get("value")
    if claim.verb.data_type.name.endswith("directed_link"):
        # no longer allowed
        value = O.Claim(int(value))
    else:
        value = O.Plain.from_form(claim.verb, form)
    claim.set_value(value)
    return redirect(f"/claims/{claim_id}")


@app.post("/claims/<claim_id>/move")
async def move_claim(request, claim_id: int):
    form = D(request.form)
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    value = form.get("value")
    claim.set_subject(O.Claim(int(value)))
    return redirect(f"/claims/{claim_id}")


@app.get("/verbs")
@page
async def list_verbs(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, verb in enumerate(
        O.Verb.all(
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,
        )
    ):
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
@admin_only
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
                {
            "".join(
                f'''<option value="{data_type}">{data_type}</option>'''
                for data_type in TYPES
            )
        }
            </select>
            <span id="steps"></span>
        </form>
    """


@app.get("/verbs/new/steps")
@admin_only
@fragment
async def new_verb_form_steps(request):
    args = D(request.args)
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">»</button>'


@app.post("/verbs/new")
@admin_only
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
    for i, query in enumerate(
        O.Query.all(
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,
        )
    ):
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
@admin_only
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
@admin_only
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
    SPECIAL_COL_NAMES[singular] = lambda value, model=model: model(int(value))
    SPECIAL_COL_NAMES[plural] = lambda value, model=model: ", ".join(
        str(model(int(part))) for part in value.split(",")
    )


def display_query_result(result):
    if result:
        header = dict(result[0]).keys()
        colmap = {}
        for col in header:
            prefix, _, type_ = col.rpartition("_")
            if type_ in SPECIAL_COL_NAMES:
                colmap[col] = {"label": prefix, "display": SPECIAL_COL_NAMES[type_]}
            else:
                colmap[col] = {"label": col, "display": str}
        parts = [
            "<table><thead><tr>",
            *(f"<td>{colmap[col]['label']}</td>" for col in header),
            "</tr></thead><tbody>",
        ]
        for row in result:
            parts.append("<tr>")
            for col in header:
                try:
                    parts.append(f"<td>{colmap[col]['display'](row[col])}</td>")
                except (ValueError, TypeError):
                    parts.append(f"<td>{row[col]}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
        return "".join(parts)
    return ""


@app.post("/queries/preview")
@admin_only
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
@admin_only
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
@admin_only
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
    if not context.user.can("view", "query", query_id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    page_no = int(request.args.get("page", 1))
    query = O.Query(query_id)
    result = query.run(
        page_no=page_no - 1,
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
        {
            pagination(
                f"/queries/{query_id}",
                page_no,
                more_results=more_results,
            )
        }
        </article>
    """


@app.get("/comments")
@page
async def list_comments(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, claim in enumerate(
        O.Claim.all_comments(
            order_by="id DESC",
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,  # so we know if there would be more results
        )
    ):
        if i:
            parts.append("<br>")
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"{claim:link}")
    return "Comments", "".join(parts) + pagination(
        "/comments",
        page_no,
        more_results=more_results,
    )


@app.get("/claims")
@page
async def list_labelled_claims(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, claim in enumerate(
        O.Claim.all_labelled(
            order_by="id DESC",
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,  # so we know if there would be more results
        )
    ):
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
    if not context.user.can("read", "verb", claim.verb.id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    incoming_mentions = list(claim.incoming_mentions())
    comments = list(claim.comments())
    return f"{claim:label}", f"""
        <article>
            <header>{claim:heading}{claim:avatar}</header>
            <div id="edit-area"></div>
            <table class="claims"><tr><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/incoming" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        {"".join(f'<span class="row">{c:sv}</span>' for c in claim.incoming_claims())}
        </td><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/outgoing" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        {"".join(f'<span class="row">{c:vo:{claim_id}}</span>' for c in claim.outgoing_claims() if c.verb.id not in (LABEL, IS_A, AVATAR, COMMENT))}
        </td></tr></table>
        {"<hr><h3>Mentions</h3>" + "".join(f'<span class="row">{c:svo}</span>' for c in incoming_mentions) if incoming_mentions else ""}
        <footer>
        {'<table class="comments">' + "".join(f"{c:comment}" for c in comments) + "</table>" if comments else ""}
        {
        f'''<form method="POST" action="/claims/new/{claim_id}/outgoing">
            <input type="hidden" name="verb" value="{COMMENT}">
            <input name="value" placeholder="Add comment...">
            <input type="submit" hidden>
        </form>''' if context.user.can("write", "verb", COMMENT) else ""
        }
        </footer>
        </article>
    """


@app.get("/verbs/<verb_id>")
@page
async def view_verb(request, verb_id: int):
    page_no = int(request.args.get("page", 1))
    if not context.user.can("read", "verb", verb_id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verb = O.Verb(verb_id)
    parts = [f'<article><header>{verb:heading}</header><div id="edit-area"></div>']
    more_results = False
    for i, claim in enumerate(
        verb.claims(
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,  # so we know if there would be more results
        )
    ):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f'<span class="row">{claim:svo}</span>')
    parts.append("</article>")
    return verb.label, "".join(parts) + pagination(
        f"/verbs/{verb_id}",
        page_no,
        more_results=more_results,
    )


@app.get("/users")
@admin_only
@page
async def list_users(request):
    page_no = int(request.args.get("page", 1))
    parts = [
        "<article><header><h3>Users</h3></header><table>",
        '<thead><tr><th scope="col">ID</th><th scope="col">Name</th></tr></thead>',
        "<tbody>",
    ]
    more_results = False
    for i, user in enumerate(
        O.User.all(
            page_no=page_no - 1,
            page_size=PAGE_SIZE + 1,
        )
    ):
        if i == PAGE_SIZE:
            more_results = True
        else:
            parts.append(f"<tr><td>{user.id}</td>")
            parts.append(f"<td>{user:link}</td></tr>")
    parts.append("</tbody></table></article>")
    return "Users", "".join(parts) + pagination(
        "/users",
        page_no,
        more_results=more_results,
    )


def _user_form(*, password_input, endpoint, user=None):
    verb_options_r, verb_options_w, query_options = [], [], []
    for verb in O.Verb.all(page_size=9999):
        if verb.id < 0:
            verb_options_w.append(
                f'<option {"selected" if user and user.can("write", "verb", verb.id) else ""} value="{verb.id}">{verb.label}</option>'
            )
            continue
        verb_options_r.append(
            f'<option {"selected" if user and user.can("read", "verb", verb.id) else ""} value="{verb.id}">{verb.label}</option>'
        )
        verb_options_w.append(
            f'<option {"selected" if user and user.can("write", "verb", verb.id) else ""} value="{verb.id}">{verb.label}</option>'
        )
    for query in O.Query.all(page_size=9999):
        query_options.append(
            f'<option {"selected" if user and user.can("view", "query", query.id) else ""} value="{query.id}">{query.label}</option>'
        )
    verb_options_r = "\n".join(verb_options_r)
    verb_options_w = "\n".join(verb_options_w)
    query_options = "\n".join(query_options)

    return f"""
        <form
            action="{endpoint}"
            method="POST"
        >
            <input name="name" placeholder="name" value="{user and user.name or ''}">
            {'' if user and user.is_admin else f'''
            <h3>Readable verbs</h3>
            <select name="verbs-readable" multiple size="10">
            {verb_options_r}
            </select>

            <h3>Writable verbs</h3>
            <select name="verbs-writable" multiple size="10">
            {verb_options_w}
            </select>

            <h3>Viewable queries</h3>
            <select name="queries-viewable" multiple size="10">
            {query_options}
            </select>
            '''}

            {password_input}

            <input type="submit" value="{'Save' if user else 'Create'}">
        </form>
    """



@app.get("/users/new")
@admin_only
@page
async def new_user_form(request):
    password = token_urlsafe(16)
    return "New user", _user_form(endpoint="/users/new", password_input=f"""
        <fieldset role="group">
        <input id="password" disabled value="{password}">
        <input type="hidden" name="password" value="{password}">
        <input type="button" value="copy" onclick="navigator.clipboard.writeText('{password}')">
        </fieldset>
    """)


@app.get("/users/<user_id>/edit")
@admin_only
@page
async def edit_user_form(request, user_id: int):
    user = O.User(user_id)
    return f"Edit user {user.name}", _user_form(user=user, endpoint=f"/users/{user_id}/edit", password_input="""
        <label>New password
        <input type="password" name="password" value="" placeholder="(leave empty to keep as-is)">
        </label>
    """)


@app.get("/verbs/<verb_id>/edit")
@admin_only
@fragment
async def edit_verb_form(request, verb_id: int):
    verb = O.Verb(verb_id)
    return f"""
        <form
            action="/verbs/{verb_id}/edit"
            method="POST"
        >
            <input name="label" value="{verb.label}">
            <button type="submit">»</button>
        </form>
        """


@app.post("/verbs/<verb_id>/edit")
@admin_only
async def edit_verb(request, verb_id: int):
    form = D(request.form)
    verb = O.Verb(verb_id)
    value = form.get("label")
    verb.rename(value)
    return redirect(f"/verbs/{verb_id}")


def _write_user(form, endpoint, user=None):
    writable_verbs = {int(v) for v in form["verbs-writable"]} if "verbs-writable" in form else set()
    readable_verbs = {int(v) for v in form["verbs-readable"]} if "verbs-readable" in form else set()
    viewable_queries = {int(v) for v in form["queries-viewable"]} if "queries-viewable" in form else set()
    if ROOT in writable_verbs and (IS_A not in writable_verbs or LABEL not in writable_verbs):
        return redirect(f"{endpoint}?err=When making the root verb writable, you also need to make category and label writable.")
    if any(v >= 0 for v in writable_verbs - readable_verbs):
        return redirect(f"{endpoint}?err=All writable verbs need to be readable.")

    if user:
        user.update(
            name=form.get("name"),
            password=form.get("password"),
            readable_verbs=readable_verbs,
            writable_verbs=writable_verbs,
            viewable_queries=viewable_queries,
        )
    else:
        user = O.User.new(
            name=form.get("name"),
            password=form.get("password") if "password" in form else None,
            readable_verbs=readable_verbs,
            writable_verbs=writable_verbs,
            viewable_queries=viewable_queries,
        )
    return redirect(f"/users/{user.id}")


@app.post("/users/<user_id>/edit")
@admin_only
async def edit_user(request, user_id: int):
    user = O.User(user_id)
    return _write_user(request.form, endpoint=f"/users/{user_id}/edit", user=user)


@app.post("/users/new")
@admin_only
async def new_user(request):
    return _write_user(request.form, endpoint="/users/new")


@app.get("/users/<user_id>")
@admin_only
@page
async def view_user(request, user_id: int):
    user = O.User(user_id)
    result = f"""
        <article><header>
        <a
            href="/users/{user_id}/edit"
            role="button"
            class="outline contrast toolbutton"
        >✎ Edit</a>
        <h3>{user:heading}</h3>
        </header>
        <table>
        <tr><th scope="row">Admin</th><td>{TYPES["boolean"].display_html(user.is_admin)}</td></tr>
        <tr><th scope="row">Readable verbs</th><td>{", ".join(str(O.Verb(v)) for v in (user.readable_verbs or []) if v >= 0)}</td></tr>
        <tr><th scope="row">Writable verbs</th><td>{", ".join(str(O.Verb(v)) for v in (user.writable_verbs or []))}</td></tr>
        <tr><th scope="row">Viewable queries</th><td>{", ".join(str(O.Query(q)) for q in (user.viewable_queries or []))}</td></tr>
        </table>
        </article>
    """
    return user.name, result


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("data/htmx.js", mime_type="text/javascript")


@app.get("/style.css")
async def style_css(request):
    return await file("data/style.css", mime_type="text/css")


@app.get("/mana-cost.css")
async def mana_cost_css(request):
    return await file("data/mana-cost.css", mime_type="text/css")


@app.get("/mana.svg")
async def mana_svg(request):
    return await file("data/mana.svg", mime_type="image/svg+xml")


@app.get("/prism.css")
async def prism_css(request):
    return await file("data/prism.css", mime_type="text/css")


@app.get("/pico.min.css")
async def pico_css(request):
    return await file("data/pico.min.css", mime_type="text/css")


@app.get("/prism.js")
async def prism_js(request):
    return await file("data/prism.js", mime_type="text/javascript")


@app.get("/cytoscape.min.js")
async def cytoscape_js(request):
    return await file("data/cytoscape.min.js", mime_type="text/javascript")


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("data/favicon.ico", mime_type="image/x-icon")


@app.get("/logo.svg")
async def logo_svg(request):
    return await file("data/logo.svg", mime_type="image/svg+xml")
