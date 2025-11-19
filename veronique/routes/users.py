from secrets import token_urlsafe

from sanic import Blueprint, redirect

import veronique.objects as O
from veronique.utils import page, admin_only, pagination
from veronique.settings import settings as S
from veronique.data_types import TYPES
from veronique.db import LABEL, IS_A, ROOT

users = Blueprint("users", url_prefix="/users")


@users.get("/")
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
            page_size=S.page_size + 1,
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f"<tr><td>{user.id}</td>")
            parts.append(f"<td>{user:link}</td></tr>")
    parts.append("</tbody></table>")
    parts.append(pagination(
        "/users",
        page_no,
        more_results=more_results,
    ))
    parts.append("</article>")
    return "Users", "".join(parts)


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



@users.get("/new")
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


@users.get("/<user_id>/edit")
@admin_only
@page
async def edit_user_form(request, user_id: int):
    user = O.User(user_id)
    return f"Edit user {user.name}", _user_form(user=user, endpoint=f"/users/{user_id}/edit", password_input="""
        <label>New password
        <input type="password" name="password" value="" placeholder="(leave empty to keep as-is)">
        </label>
    """)


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


@users.post("/<user_id>/edit")
@admin_only
async def edit_user(request, user_id: int):
    user = O.User(user_id)
    return _write_user(request.form, endpoint=f"/users/{user_id}/edit", user=user)


@users.post("/new")
@admin_only
async def new_user(request):
    return _write_user(request.form, endpoint="/users/new")


@users.get("/<user_id>")
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
