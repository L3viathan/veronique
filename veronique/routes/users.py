from secrets import token_urlsafe

from sanic import Blueprint, html, redirect

import veronique.objects as O
from veronique.autocomplete import AUTOCOMPLETES
from veronique.context import context
from veronique.data_types import TYPES
from veronique.db import IS_A, ROOT
from veronique.html import H, join
from veronique.settings import settings as S
from veronique.utils import admin_only, page, pagination

users = Blueprint("users", url_prefix="/users")


@users.get("/")
@admin_only
@page
async def list_users(request):
    page_no = int(request.args.get("page", 1))
    users = []
    more_results = False
    for i, user in enumerate(
        O.User.all(
            page_no=page_no - 1,
            page_size=S.page_size + 1,
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            users.append(
                H.tr(
                    H.td(str(user.id)),
                    H.td(user.html("link")),
                    H.td(user.html("session")),
                    H.td(
                        H.button(
                            "Impersonate",
                            cls="danger",
                            hx_post=f"/users/{user.id}/impersonate",
                        )
                    ) if context.user.id != user.id else H.td("")
                ),
            )
    return "Users", H.article(
        H.header(H.h3("Users")),
        H.table(
            H.thead(
                H.tr(
                    H.th("ID", scope="col"),
                    H.th("Name", scope="col"),
                    H.th("Session", scope="col"),
                    H.th("Impersonate", scope="col"),
                ),
            ),
            H.tbody(*users),
        ),
        pagination(
            "/users",
            page_no,
            more_results=more_results,
        ),
    )


def _user_form(*, password_input, endpoint, user=None):
    verb_options_r, verb_options_w, query_options = [], [], []
    for verb in O.Verb.all(page_size=9999):
        if verb.id < 0:
            verb_options_w.append(
                H.option(
                    verb.label,
                    selected=user and user.can("write", "verb", verb.id),
                    value=str(verb.id),
                )
            )
            continue
        verb_options_r.append(
            H.option(
                verb.label,
                selected=user and user.can("read", "verb", verb.id),
                value=str(verb.id),
            )
        )
        if verb.data_type != TYPES["inferred"]:
            verb_options_w.append(
                H.option(
                    verb.label,
                    selected=user and user.can("write", "verb", verb.id),
                    value=str(verb.id),
                )
            )
    for query in O.Query.all(page_size=9999):
        query_options.append(
            H.option(
                query.label,
                selected=user and user.can("view", "query", query.id),
                value=str(query.id),
            )
        )

    return H.form(
        H.input(
            name="name",
            placeholder="name",
            value=user and user.name or "",
        ),
        H.label(
            H.input(name="redact", type="checkbox", role="switch", checked=bool(user and user.redact)),
            "Redact PII for this user",
        ),
        None if user and user.is_admin else H(
            H.h3("Readable verbs"),
            H.select(*verb_options_r, name="verbs-readable", multiple=True, size="10"),
            H.h3("Writable verbs"),
            H.select(*verb_options_w, name="verbs-writable", multiple=True, size="10"),
            H.h3("Viewable queries"),
            H.select(*query_options, name="queries-viewable", multiple=True, size="10"),
        ),
        H.h3("Corresponding entity"),
        str(user and user.entity or ""),
        AUTOCOMPLETES["entity"].widget(None),
        password_input,
        H.input(type="submit", value="Save" if user else "Create"),
        action=endpoint,
        method="POST",
    )


@users.get("/new")
@admin_only
@page
async def new_user_form(request):
    password = token_urlsafe(16)
    return "New user", _user_form(
        endpoint="/users/new",
        password_input=H.fieldset(
            H.input(id="password", disabled=True, value=password),
            H.input(type="hidden", name="password", value=password),
            H.input(type="button", value="copy", onclick=f"navigator.clipboard.writeText('{password}')"),
            role="group",
        ),
    )


@users.get("/<user_id>/edit")
@admin_only
@page
async def edit_user_form(request, user_id: int):
    user = O.User(user_id)
    return f"Edit user {user.name}", _user_form(
        user=user,
        endpoint=f"/users/{user_id}/edit",
        password_input=H.label(
            "New password",
            H.input(type="password", name="password", value="", placeholder="(leave empty to keep as-is)"),
        ),
    )


def _write_user(form, endpoint, user=None):
    writable_verbs = {int(v) for v in form["verbs-writable"]} if "verbs-writable" in form else set()
    readable_verbs = {int(v) for v in form["verbs-readable"]} if "verbs-readable" in form else set()
    viewable_queries = {int(v) for v in form["queries-viewable"]} if "queries-viewable" in form else set()
    redact = "redact" in form
    if "entity_id" in form:
        [entity_id] = form["entity_id"]
    else:
        entity_id = None
    if writable_verbs and redact:
        return redirect(f"{endpoint}?err=For now, users that can write can't have a redacted view.")
    if ROOT in writable_verbs and IS_A not in writable_verbs:
        return redirect(f"{endpoint}?err=When making the root verb writable, you also need to make category writable.")
    if any(v >= 0 for v in writable_verbs - readable_verbs):
        return redirect(f"{endpoint}?err=All writable verbs need to be readable.")

    if user:
        user.update(
            name=form.get("name"),
            password=form.get("password"),
            readable_verbs=readable_verbs,
            writable_verbs=writable_verbs,
            viewable_queries=viewable_queries,
            redact=redact,
            entity_id=entity_id,
        )
    else:
        user = O.User.new(
            name=form.get("name"),
            password=form.get("password") if "password" in form else None,
            readable_verbs=readable_verbs,
            writable_verbs=writable_verbs,
            viewable_queries=viewable_queries,
            redact=redact,
            entity_id=entity_id,
        )
    return redirect(f"/users/{user.id}")


@users.post("/<user_id>/edit")
@admin_only
async def edit_user(request, user_id: int):
    user = O.User(user_id)
    return _write_user(request.form, endpoint=f"/users/{user_id}/edit", user=user)


@users.post("/new")
@admin_only
async def new_user(request):
    return _write_user(request.form, endpoint="/users/new")


@users.post("/<user_id>/impersonate")
@admin_only
async def impersonate_user(request, user_id):
    response = html("""
        <meta http-equiv="refresh" content="0; url=/">
    """)
    response.add_cookie(
        "impersonate",
        user_id,
        httponly=True,
    )
    return response


@users.post("/stop-impersonating")
async def stop_impersonating(request):
    redirect_url = request.headers.get("hx-current-url") or "/"
    response = html(f"""
        <meta http-equiv="refresh" content="0; url={redirect_url}">
    """)
    response.delete_cookie("impersonate")
    del context.impersonator
    return response


@users.get("/<user_id>")
@admin_only
@page
async def view_user(request, user_id: int):
    user = O.User(user_id)
    readable_verbs, writable_verbs, viewable_queries = [], [], []
    for v in user.readable_verbs or []:
        if v < 0:
            continue
        try:
            readable_verbs.append(O.Verb(v))
        except ValueError:
            continue
    for v in user.writable_verbs or []:
        try:
            writable_verbs.append(O.Verb(v))
        except ValueError:
            continue
    for v in user.viewable_queries or []:
        try:
            viewable_queries.append(O.Query(v))
        except ValueError:
            continue
    return user.name, H.article(
        H.header(
            H.h3(user.html("heading")),
            user.html("hamburger"),
        ),
        H.table(
            H.tr(H.th("Session", scope="row"), H.td(user.html("session"))),
            H.tr(H.th("Admin", scope="row"), H.td(TYPES["boolean"].display_html(user.is_admin))),
            H.tr(H.th("Redact", scope="row"), H.td(TYPES["boolean"].display_html(user.redact))),
            H.tr(H.th("Readable verbs", scope="row"), H.td(*join(", ", (v.html() for v in readable_verbs)))),
            H.tr(H.th("Writable verbs", scope="row"), H.td(*join(", ", (v.html() for v in writable_verbs)))),
            H.tr(H.th("Viewable queries", scope="row"), H.td(*join(", ", (q.html() for q in viewable_queries)))),
        )
    )
