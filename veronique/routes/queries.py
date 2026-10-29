import sqlite3

from sanic import Blueprint, HTTPResponse, json

import veronique.objects as O
from veronique import db
from veronique.context import context
from veronique.data_types import TYPES
from veronique.html import H
from veronique.network import network_widget
from veronique.settings import settings as S
from veronique.utils import D, admin_only, fragment, page, pagination

queries = Blueprint("queries", url_prefix="/queries")


@queries.get("/")
@page
async def list_queries(request):
    page_no = int(request.args.get("page", 1))
    queries = []
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
            queries.append(H.span(query.html("full"), cls="row"))
    return "Queries", H.article(
        *queries,
        pagination(
            "/queries",
            page_no,
            more_results=more_results,
        ),
    )


def _queries_form_elements(query=None):
    return H(
        H.input(name="label", placeholder="label", value=query and query.label),
        H.div(
            H.textarea(
                str(query and query.sql or ""),
                id="editing",
                name="sql",
                spellcheck="false",
                oninput="update(this.value); sync_scroll(this);",
                onscroll="sync_scroll(this);",
                onload="setTimeout(function(){{update(this.value); sync_scroll(this);}}, 100)",
            ),
            H.pre(
                H.code(
                    str(query and query.sql or ""),
                    cls="language-sql",
                    id="highlighting-content",
                ),
                id="highlighting",
                aria_hidden="true",
            ),
        ),
        H.div(
            H.button(
                "Preview",
                cls="secondary",
                hx_post="/queries/preview",
                hx_target="#preview",
                hx_include="#editing",
                hx_swap="innerMorph",
            ),
            H.button("\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}", type="submit"),
            role="group",
        ),
        H.div("", id="preview"),
    )


@queries.get("/new")
@admin_only
@page
async def new_query_form(request):
    return "New query", H.form(
        _queries_form_elements(),
        hx_post="/queries/new",
        hx_encoding="multipart/form-data",
    )


@queries.get("/<query_id>/edit")
@admin_only
@page
async def edit_query_form(request, query_id: int):
    query = O.Query(query_id)
    return f"Edit {query.label!r}", H.form(
        _queries_form_elements(query),
        hx_put=query.url(),
        hx_swap="outerMorph",
        hx_encoding="multipart/form-data",
    )


SPECIAL_COL_NAMES = {}
for singular, plural, model in (
    ("c", "cs", O.Claim),
    ("v", "vs", O.Verb),
):
    SPECIAL_COL_NAMES[singular] = lambda value, model=model: str(model(int(value)))
    SPECIAL_COL_NAMES[plural] = lambda value, model=model: ", ".join(
        str(model(int(part))) for part in value.split(",")
    )

for dt_name, data_type in TYPES.items():
    SPECIAL_COL_NAMES[dt_name] = lambda value, dt=data_type: dt.display_html(value)


def display_query_result(result, query=None):
    if result:
        header = dict(result[0]).keys()
        colmap = {}
        for col in header:
            prefix, _, type_ = col.rpartition("_")
            if type_ in SPECIAL_COL_NAMES and prefix:
                colmap[col] = {"label": prefix, "display": SPECIAL_COL_NAMES[type_]}
            else:
                colmap[col] = {"label": col, "display": str}
        headers = []
        for col in header:
            if col.endswith("_c") and query is not None:
                headers.append(H.td(colmap[col]["label"], H.a(H.small("[N]"), href=query.url(f"network/{col}"))))
            else:
                headers.append(H.td(colmap[col]["label"]))

        rows = []
        for row in result:
            new_row = []
            for col in header:
                try:
                    new_row.append(H.td(colmap[col]['display'](row[col])))
                except (ValueError, TypeError):
                    new_row.append(H.td(row[col]))
            rows.append(H.tr(*new_row))
        return H.table(
            H.thead(
                H.tr(*headers),
            ),
            H.tbody(*rows),
        )
    return None


@queries.post("/preview")
@admin_only
@fragment
async def preview_query(request):
    form = D(request.form)
    res = None
    try:
        cur = db.conn.cursor()
        res = cur.execute(form["sql"] + " LIMIT 10").fetchall()
    except (sqlite3.Warning, sqlite3.OperationalError) as e:
        return H.article(H.strong("Error:"), f" {e.args[0]}", cls="error")
    finally:
        db.conn.rollback()
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
    return H.meta(http_equiv="refresh", content=f"0; url={query.url()}")


@queries.put("/<query_id>")
@admin_only
@fragment
async def edit_query(request, query_id: int):
    query = O.Query(query_id)
    form = D(request.form)
    query.update(label=form["label"], sql=form["sql"])
    return H.meta(http_equiv="refresh", content=f"0; url={query.url()}")


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
    form_elements, bindings = query.bind(request.args)
    if form_elements:
        form_elements = H.form(*form_elements)
    else:
        form_elements = None
    if bindings is not None:
        result = query.run(
            bindings,
            page_no=page_no - 1,
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
        if len(result) > S.page_size:
            more_results = True
            result = result[:-1]
        else:
            more_results = False
        results = display_query_result(result, query=query)
    else:
        results = None
    if request.host:
        qpath = request.url.partition(request.host)[2]
    else:
        qpath = request.url.removeprefix("https://").removeprefix("http://")
    return query.label, H.article(
        H.header(
            query.html("heading"),
            query.html("hamburger"),
            form_elements,
        ),
        H.div(
            results,
            pagination(
                qpath,
                page_no,
                more_results=more_results,
            ) if results else None,
            id="queryresults",
        ),
    )


@queries.get("/<query_id>/network/<col>")
@page
async def view_query_graph(request, query_id: int, col: str):
    if not context.user.can("view", "query", query_id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    query = O.Query(query_id)
    result = query.run(
        {},  # no bindings
        page_no=0,
        page_size=9999,
    )
    claims = (O.Claim(row[col]) for row in result)
    return f"{query.label} [N]", network_widget(claims)


@queries.delete("/<query_id>")
@fragment
async def delete_query(request, query_id: int):
    query = O.Query(query_id)
    if not context.user.is_admin:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    query.delete()
    return H.meta(http_equiv="refresh", content="0; url=/queries")


@queries.post("/remote")
@admin_only
async def remote_query(request):
    query = request.json["q"]
    params = request.json.get("p", {})
    try:
        cur = db.conn.cursor()
        res = cur.execute(query, params).fetchall()
    except (sqlite3.Warning, sqlite3.OperationalError, sqlite3.ProgrammingError) as e:
        print("E:", e.args[0], "for", query, "with", params)
        return HTTPResponse(
            body=e.args[0],
            status=400,
        )
    finally:
        db.conn.rollback()
    return json([dict(row) for row in res])
