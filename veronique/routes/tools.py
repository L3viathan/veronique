from sanic import Blueprint, HTTPResponse, redirect, raw

import veronique.objects as O
from veronique.utils import fragment, page, pagination, D
from veronique.data_types import TYPES
from veronique.settings import settings as S
from veronique.context import context
from veronique.db import IS_A, ROOT, AVATAR, COMMENT
from veronique.autocomplete import AUTOCOMPLETES

tools = Blueprint("tools", url_prefix="/tools")


@tools.get("connections")
@page
async def get_connections_form(request):
    widget = AUTOCOMPLETES["connections"].widget()
    return f"""
    <h2>What connects these claims?</h2>
    <form
        hx-post="/tools/connections"
        hx-encoding="multipart/form-data"
    >
        {widget}
        <button type="submit">Find connections</button>
    </form>
    """


@tools.post("connections")
async def redirect_to_network(request):
    claim_ids = ",".join(request.form["value"])
    return redirect(f"/network?claims={claim_ids}")
