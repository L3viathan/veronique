import functools
import re
from datetime import date, datetime, timedelta
from sanic import Sanic, html, file, redirect

import veronique.objects as O
import veronique.security as security
from veronique.context import context
from veronique.settings import settings as S
from veronique.nomnidate import NonOmniscientDate
from veronique.db import ROOT
from veronique.utils import page, coalesce, pagination, D, _notice
from veronique.routes import claims, verbs, queries, users, settings, network

app = Sanic("Veronique")
app.blueprint(claims)
app.blueprint(verbs)
app.blueprint(queries)
app.blueprint(users)
app.blueprint(settings)
app.blueprint(network)

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
        {_notice('There are <a href="/claims/comments">unresolved comments</a>') if context.user.is_admin and list(O.Claim.all_comments()) else ""}
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
