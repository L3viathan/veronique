from sanic import Blueprint

from veronique.autocomplete import Tags, accept, get_results
from veronique.html import H
from veronique.utils import D, fragment

autocomplete = Blueprint("autocomplete", url_prefix="/autocomplete")


@autocomplete.get("/query")
@fragment
def query_autocomplete(request):
    args = D(request.args)
    query = args.get("ac-query", "")
    tags = args.get("tags", "")
    return get_results(query, Tags(tags))


@autocomplete.get("/accept/<hit>")
@fragment
def accept_autocomplete(request, hit):
    tags = D(request.args).get("tags", "")
    return accept(hit, Tags(tags))


@autocomplete.get("/cancel")
@fragment
def cancel_autocomplete(request):
    tags = D(request.args).get("tags", "")
    if "ir" in tags:
        return H("@")
    return None
