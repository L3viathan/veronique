import sqlite3

from sanic import Blueprint, HTTPResponse

import veronique.objects as O
from veronique.settings import settings as S
from veronique.utils import fragment, page, admin_only, pagination, D
from veronique.context import context
from veronique.db import conn

queries = Blueprint("queries", url_prefix="/queries")


@queries.get("/")
@page
async def list_queries(request):
    page_no = int(request.args.get("page", 1))
    parts = ["<article>"]
    more_results = False
    for i, query in enumerate(
        O.Query.all(
            page_no=page_no - 1,
            page_size=S.page_size + 1,
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f'<span class="row">{query:full}</span>')
    parts.append(pagination(
        "/queries",
        page_no,
        more_results=more_results,
    ))
    parts.append("</article>")
    return "Queries", "".join(parts)


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


@queries.get("/new")
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


@queries.get("/<query_id>/edit")
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


def display_query_result(result, query_id=None):
    if result:
        header = dict(result[0]).keys()
        colmap = {}
        for col in header:
            prefix, _, type_ = col.rpartition("_")
            if type_ in SPECIAL_COL_NAMES:
                colmap[col] = {"label": prefix, "display": SPECIAL_COL_NAMES[type_]}
            else:
                colmap[col] = {"label": col, "display": str}
        parts = ["<table><thead><tr>"]
        for col in header:
            print("col:", col)
            if col.endswith("_c") and query_id is not None:
                parts.append(f'<td>{colmap[col]["label"]} <a href="/network/?query={query_id}&col={col}">🖧</a></td>')
            else:
                parts.append(f"<td>{colmap[col]['label']}</td>")

        parts.append("</tr></thead><tbody>")
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


@queries.post("/preview")
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


@queries.post("/new")
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


@queries.put("/<query_id>")
@admin_only
@fragment
async def edit_query(request, query_id: int):
    query = O.Query(query_id)
    form = D(request.form)
    query.update(label=form["label"], sql=form["sql"])
    return f"""
        <meta http-equiv="refresh" content="0; url=/queries/{query_id}">
    """


@queries.get("/<query_id>")
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
        page_size=S.page_size + 1,  # so we know if there would be more results
    )
    if len(result) > S.page_size:
        more_results = True
        result = result[:-1]
    else:
        more_results = False
    return query.label, f"""
        <article><header>
        {query:heading}</header>{display_query_result(result, query_id=query_id)}
        {
            pagination(
                f"/queries/{query_id}",
                page_no,
                more_results=more_results,
            )
        }
        </article>
    """
