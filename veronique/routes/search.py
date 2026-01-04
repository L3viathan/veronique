from sanic import Blueprint

import veronique.objects as O
from veronique.settings import settings as S
from veronique.context import context
from veronique.utils import page, pagination, D, admin_only, fragment
from veronique.db import conn
from veronique.search import rebuild_search_index, find


search = Blueprint("search", url_prefix="/search")


@search.get("/")
@page
async def perform_search(request):
    page_no = int(request.args.get("page", 1))
    query = D(request.args).get("q", "")
    cur = conn.cursor()
    hits = find(
        cur, query, page_size=S.page_size + 1, page_no=page_no - 1
    )
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


@search.post("/rebuild")
@admin_only
@fragment
async def rebuild_search(request):
    cur = conn.cursor()
    rebuild_search_index(cur)
    return "<em>successfully rebuilt</em>"
