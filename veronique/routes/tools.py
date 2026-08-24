from collections import defaultdict, deque
from itertools import combinations
from time import monotonic

from sanic import Blueprint, redirect

import veronique.objects as O
from veronique.autocomplete import AUTOCOMPLETES
from veronique.context import context
from veronique.network import network_widget
from veronique.utils import admin_only, page

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
@page
async def redirect_to_network(request):
    claim_ids = [int(claim_id) for claim_id in request.form["value"]]
    colormap = defaultdict(lambda: 0)
    for claim_id in claim_ids:
        colormap[str(claim_id)] = 1
    claims = set()
    t_start = monotonic()
    for a_id, b_id in combinations(claim_ids, 2):
        a = O.Claim(a_id)
        queue = deque([(a, [])])
        results = None
        while queue and not results:
            t, p = queue.popleft()
            for link in t.all_links(page_size=999):
                r_id = link.subject.id if link.subject.id != t.id else link.object.id
                if r_id in (pe.id for pe in p):
                    continue
                r = O.Claim(r_id)
                p_ = [*p, r]
                if r_id == b_id:
                    results = p_
                else:
                    queue.append((r, p_))
            if monotonic() - t_start > 5:
                return redirect("/")

        if results:
            claims.add(a)
            claims.update(results)
    return "Connections", network_widget(claims, colormap=colormap)


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


@tools.get("bulk-claim")
@page
async def get_bulk_claim_form(request):
    widget = AUTOCOMPLETES["multiselect"].widget()
    return f"""
    <h2>New bulk claim</h2>
    <form
        action="/tools/bulk-claim"
        method="POST"
        enctype="multipart/form-data"
    >
        {widget}
        <button type="submit">Make bulk claim</button>
    </form>
    """


@tools.post("bulk-claim")
@page
async def start_bulk_claim(request):
    claim_ids = request.form["value"]
    claims = [O.Claim(int(claim_id)) for claim_id in claim_ids]
    return "New bulk claim", f"""
        <article>
            <header><h2>New bulk claim</h2>{' '.join(f"{claim}" for claim in claims)}</header>
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
