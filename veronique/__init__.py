import re
from datetime import datetime, timedelta
from sanic import Sanic, html, file, redirect

import veronique.objects as O
import veronique.security as security
from veronique.context import context
from veronique.utils import D
from veronique.routes import claims, verbs, queries, users, settings, network, static, index, search

app = Sanic("Veronique")
app.blueprint(claims)
app.blueprint(verbs)
app.blueprint(queries)
app.blueprint(users)
app.blueprint(settings)
app.blueprint(network)
app.blueprint(static)
app.blueprint(index)
app.blueprint(search)

with open("data/login.html") as f:
    LOGIN = f.read()


@app.on_request
async def auth(request):
    """Ensure that each request is either authenticated or going to an explicitly allowed resource."""
    if request.route and (
        request.route.path == "login"
        or request.route.path.endswith((".css", ".js", ".svg"))
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


@app.get("/favicon.ico")
async def favicon_ico(request):
    return await file("data/favicon.ico", mime_type="image/x-icon")
