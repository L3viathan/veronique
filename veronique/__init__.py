import re
from datetime import datetime

from sanic import Sanic, file, redirect
from sanic import html as sanic_html  # Why the fuck is this needed?

import veronique.objects as O
from veronique import security
from veronique.constants import SESSION_MAX_AGE, SESSION_REFRESH_AFTER
from veronique.context import context
from veronique.routes import (
    autocomplete,
    claims,
    index,
    queries,
    search,
    settings,
    static,
    tools,
    types,
    users,
    verbs,
)
from veronique.templates import LOGIN
from veronique.utils import D

app = Sanic("Veronique")
app.blueprint(claims)
app.blueprint(verbs)
app.blueprint(queries)
app.blueprint(users)
app.blueprint(settings)
app.blueprint(static)
app.blueprint(index)
app.blueprint(search)
app.blueprint(tools)
app.blueprint(types)
app.blueprint(autocomplete)


@app.on_request
async def auth(request):
    """Ensure that each request is either authenticated or going to an explicitly allowed resource."""
    if request.route and (
        request.route.path == "login"
        or request.route.path.endswith((".css", ".js", ".svg", ".png"))
    ):
        # allow unauthenticated access to login page and static assets
        context.user = None
        context.payload = None
        return
    if request.method == "GET" and request.path != "/":
        # After a successful login, we want to redirect them to the path they
        # wanted to go to originally, if we can safely do so.
        unauthorized = redirect(f"/login?then={request.path}")
    else:
        unauthorized = redirect("/login")
    if payload := security.unsign(
        request.cookies.get("session") or request.headers.get("Authorization"),
    ):
        # Non-empty payload means the token presented is valid, in the sense of
        # "was legitimately issued by this instance". It does not mean that we
        # want this to be a successful login (yet):
        if (datetime.now() - datetime.fromisoformat(payload["t"])) > SESSION_MAX_AGE:
            # Sessions have a maximum age (which gets refreshed automatically
            # (see refresh_session) so this only affects the user if they
            # haven't logged in for a long time). What does this protect
            # against? Mainly credential stealing by having taken over the
            # computer of an (inactive) user. It does not protect the scenario
            # of an _active_ user's computer being taken over of course.
            return unauthorized
        user = O.User(payload["u"])
        if user.generation > payload.get("g", 0):
            # this is to support proper logouts, see logout()
            return unauthorized
        if impersonatee := request.cookies.get("impersonate"):
            if not user.is_admin:
                # Only admins may impersonate, as this feature allows acting as
                # any other user (including admins).
                return unauthorized
            context.user = O.User(int(impersonatee))
            # This is to allow showing in the UI who the _real_ user is:
            context.impersonator = user
        else:
            context.user = user
        context.payload = payload
        return
    return unauthorized


@app.on_response
async def refresh_session(request, response):
    """If authenticated requests have overly old payloads, refresh them."""
    if not (payload := context.payload):
        return
    if (datetime.now() - datetime.fromisoformat(payload["t"])) > SESSION_REFRESH_AFTER:
        # Refresh a session when it's older than SESSION_REFRESH_AFTER. By
        # making this value larger than the SESSION_MAX_AGE, the feature could
        # be disabled entirely.
        context.user.make_session(response)


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
    if "then" in request.args:
        then = request.args.get("then")
    else:
        then = ""
    return sanic_html(str(LOGIN(then=then)))


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
        if "then" in form:
            response = redirect(form["then"])
        else:
            response = redirect("/")
        user.make_session(response)
        return response
    return redirect("/login")


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("data/favicon.ico", mime_type="image/x-icon")
