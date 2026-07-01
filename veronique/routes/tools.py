from sanic import Blueprint, redirect

import veronique.objects as O
from veronique.utils import page, admin_only
from veronique.autocomplete import AUTOCOMPLETES
from veronique.context import context

tools = Blueprint("tools", url_prefix="/tools")


@tools.get("connections")
@page
async def get_connections_form(request):
    widget = AUTOCOMPLETES["multiselect"].widget()
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


@tools.get("merge")
@page
async def get_merge_form(request):
    widget = AUTOCOMPLETES["merge"].widget()
    return f"""
    <h2>Merge claims</h2>
    <form
        action="/tools/merge"
        method="POST"
        enctype="multipart/form-data"
    >
        {widget}
        <button type="submit">Merge claims</button>
    </form>
    """


@tools.post("merge")
@admin_only
async def merge_claims(request):
    claim_a, claim_b = (O.Claim(int(val)) for val in request.form["value"])
    claim_a.merge(claim_b)
    return redirect(f"/claims/{claim_a.id}")


@tools.get("multiclaims")
@page
async def get_multiclaim_form(request):
    widget = AUTOCOMPLETES["multiselect"].widget()
    return f"""
    <h2>New multiclaim</h2>
    <form
        action="/tools/multiclaims"
        method="POST"
        enctype="multipart/form-data"
    >
        {widget}
        <button type="submit">Make multiclaim</button>
    </form>
    """


@tools.post("multiclaims")
@page
async def start_multiclaim(request):
    claim_ids = request.form["value"]
    claims = [O.Claim(int(claim_id)) for claim_id in claim_ids]
    return "New multiclaim", f"""
        <article>
            <header><h2>New multiclaim</h2>{' '.join(f"{claim}" for claim in claims)}</header>
            <table class="claims"><tr><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{",".join(claim_ids)}/incoming" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        </td><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{",".join(claim_ids)}/outgoing" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        </table>
        </article>
        """
    return redirect(f"/network?claims={claim_ids}")
