from sanic import Blueprint

from veronique.utils import fragment, D
from veronique.context import context
from veronique.autocomplete import AUTOCOMPLETES

autocomplete = Blueprint("autocomplete", url_prefix="/autocomplete")


@autocomplete.get("/<variant>/query/<data>")
@fragment
def query_autocomplete(request, variant, data):
    args = D(request.args)
    query = args.get("ac-query", "")
    return AUTOCOMPLETES[variant].get_results(
        query,
        data,
    )


@autocomplete.get("/<variant>/accept/<value>")
@fragment
def accept_autocomplete(request, variant, value):
    # TODO: return everything _except_ the hidden input. That comes as OOB.
    return AUTOCOMPLETES[variant].accept(value)
