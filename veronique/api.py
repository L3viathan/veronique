import functools
import json
import re
from datetime import date, datetime, timedelta
from sanic import Sanic, html, file, redirect

import veronique.objects as O
import veronique.security as security
from veronique.context import context
from veronique.settings import settings as S
from veronique.nomnidate import NonOmniscientDate
from veronique.db import conn, IS_A, ROOT, make_search_key, rebuild_search_index
from veronique.utils import page, fragment, admin_only, coalesce, pagination, D, _notice
from veronique.routes import claims, verbs, queries, users

app = Sanic("Veronique")
app.blueprint(claims)
app.blueprint(verbs)
app.blueprint(queries)
app.blueprint(users)

with open("data/login.html") as f:
    LOGIN = f.read()


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


def _recent_events_page(request):
    recent_events = []
    page_no = int(request.args.get("page", 1))
    past_today = False
    reference_date = date.today()
    if page_no != 1:
        reference_date += timedelta(days=(S.index_days_back+S.index_days_ahead+1)*(page_no-1))
    for claim in sorted(
        O.Claim.all_near_today(reference_date, days_back=S.index_days_back, days_ahead=S.index_days_ahead),
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


def _newest_claims(request, only_root=True):
    parts = ["<article><header><h2>Newest claims</h2></header>"]
    for claim in O.Claim.all(
        verb_id=ROOT if only_root else None,
        order_by="created_at DESC",
        page_size=S.page_size,
    ):
        parts.append(f'<span class="row">{claim:link}</span>')
    parts.append("</article>")
    return "".join(parts)


@app.get("/")
@page
async def index(request):
    return {
        "recent_events": _recent_events_page,
        "newest_claims": functools.partial(_newest_claims, only_root=False),
        "newest_root_claims": _newest_claims,
    }[S.index_type](request)


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
        (make_search_key(query), S.page_size + 1, S.page_size * (page_no - 1)),
    ).fetchall()
    parts = []
    more_results = False
    for i, hit in enumerate(hits):
        if i:
            parts.append("<br>")
        if i == S.page_size:
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


@app.post("/search/rebuild")
@admin_only
@fragment
async def rebuild_search(request):
    cur = conn.cursor()
    rebuild_search_index(cur)
    return "<em>successfully rebuilt</em>"


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
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
    ):
        if i:
            parts.append("<br>")
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f"{claim:link}")
    return "Comments", "".join(parts) + pagination(
        "/comments",
        page_no,
        more_results=more_results,
    )


@app.get("/settings")
@admin_only
@page
async def settings_form(request):
    return "Settings", f"""
        <article>
            <header><h2>Settings</h2></header>
            <form method="POST">
                <h4>General</h4>
                <fieldset class="grid">
                    <label>
                    Application name
                    <input name="page_size" placeholder="Véronique">
                    <small>This will be shown as part of page titles.</small>
                    </label>
                    <label>
                    Page size
                    <input type="number" name="page_size" min=1 value="{S.page_size}">
                    <small>How many items to show in paginated pages.</small>
                    </label>
                </fieldset>
                <h4>Index page</h4>
                    <select name="index_type">
                        <option value="recent_events" {"selected" if S.index_type == "recent_events" else ""}>Recent events</option>
                        <option value="newest_root_claims" {"selected" if S.index_type == "newest_root_claims" else ""}>Newest claims (roots only)</option>
                        <option value="newest_claims" {"selected" if S.index_type == "newest_claims" else ""}>Newest claims (all)</option>
                    </select>
                <fieldset class="grid">
                    <label>
                    Days back
                    <input type="number" name="index_days_back" min=1 value="{S.index_days_back}">
                    <small>How many days to look back for relevant events.</small>
                    </label>
                    <label>
                    Days ahead
                    <input type="number" name="index_days_ahead" min=1 value="{S.index_days_ahead}">
                    <small>How many days to look forwards for relevant events.</small>
                    </label>
                </fieldset>
                <h4>Maintenance</h4>
                <fieldset>
                <a href="#" role="button" hx-swap="outerHTML" hx-post="/search/rebuild">Rebuild search index</a>
                </fieldset>

                <input type="submit" value="Save">
            </form>
        </article>
    """


@app.post("/settings")
@admin_only
async def save_settings(request):
    form = D(request.form)
    S.app_name = form.get("app_name")
    S.page_size = form.get("page_size")
    S.index_days_ahead = form.get("index_days_ahead")
    S.index_days_back = form.get("index_days_back")
    S.index_type = form.get("index_type")
    return redirect("/")


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
