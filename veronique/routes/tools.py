from sanic import Blueprint, redirect

from veronique.utils import page
from veronique.autocomplete import AUTOCOMPLETES

tools = Blueprint("tools", url_prefix="/tools")


@tools.get("connections")
@page
async def get_connections_form(request):
    widget = AUTOCOMPLETES["connections"].widget()
    return f"""
    <h2>What connects these claims?</h2>
    <form
        action="/tools/connections"
        method="POST"
        enctype="multipart/form-data"
    >
        {widget}
        <button type="submit">Find connections</button>
    </form>
    """


@tools.post("connections")
async def redirect_to_network(request):
    claim_ids = ",".join(request.form["value"])
    return redirect(f"/network?claims={claim_ids}")
