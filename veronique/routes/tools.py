from collections import defaultdict, deque
from itertools import combinations
from random import randint
from time import monotonic

from sanic import Blueprint, redirect

import veronique.objects as O
from veronique.autocomplete import Tags, widget
from veronique.constants import COORDS
from veronique.context import context
from veronique.db import LATLON
from veronique.html import H
from veronique.network import network_widget
from veronique.settings import settings as S
from veronique.utils import admin_only, page

tools = Blueprint("tools", url_prefix="/tools")


@tools.get("connections")
@page
async def get_connections_form(request):
    return H(
        H.h2("What connects these claims?"),
        H.form(
            widget(Tags("eh")),
            H.button(
                "Find connections",
                type="submit",
            ),
            action="/tools/connections",
            method="POST",
            enctype="multipart/form-data",
        ),
    )


@tools.post("connections")
@page
async def redirect_to_network(request):
    # Need to skip the first hit — it's the value of the query
    claim_ids = [int(claim_id) for claim_id in request.form["value"][1:]]
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
    return H(
        H.h2("Merge claims"),
        H.form(
            H.fieldset(
                widget(Tags("")),
                widget(Tags("")),
                cls="grid",
            ),
            H.button(
                "Merge claims",
                type="submit",
            ),
            action="/tools/merge",
            method="POST",
            enctype="multipart/form-data",
        ),
    )


@tools.post("merge")
@admin_only
async def merge_claims(request):
    claim_a, claim_b = (O.Claim(int(val)) for val in request.form["value"])
    claim_a.merge(claim_b)
    return redirect(f"/claims/{claim_a.id}")


@tools.get("bulk-claim")
@page
async def get_bulk_claim_form(request):
    return H(
        H.h2("New bulk claim"),
        H.form(
            widget(Tags("eh")),
            H.button(
                "Make bulk claim",
                type="submit",
            ),
            action="/tools/bulk-claim",
            method="POST",
            enctype="multipart/form-data",
        ),
    )


@tools.post("bulk-claim")
@page
async def start_bulk_claim(request):
    # Need to skip the first hit — it's the value of the query
    claim_ids = request.form["value"][1:]
    claims = [O.Claim(int(claim_id)) for claim_id in claim_ids]
    return "New bulk claim", H.article(
        H.header(
            H.h2("New bulk claim"),
            ' '.join(f"{claim}" for claim in claims),
        ),
        H.table(
            H.tr(
                H.td(
                    H.div(
                        "+",
                        hx_swap="outerMorph",
                        hx_get=f'/claims/new/{",".join(claim_ids)}/incoming',
                        cls="new-item-placeholder",
                    ) if context.user.is_admin or context.user.writable_verbs else ""
                ),
                H.td(
                    H.div(
                        "+",
                        hx_swap="outerMorph",
                        hx_get=f'/claims/new/{",".join(claim_ids)}/outgoing',
                        cls="new-item-placeholder",
                    ) if context.user.is_admin or context.user.writable_verbs else ""
                ),
            ),
            cls="claims",
        )
    )


@tools.get("map")
@page
async def show_map(request):
    markers = []
    if not context.user.can("read", "verb", LATLON):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    for claim in O.Claim.all(verb_id=LATLON, page_size=9999):
        if COORDS.match(claim.object.value):
            markers.append(f"""
                L.marker([{claim.object.value}], {{title: {str(claim.subject.html("label"))!r}}}).on("click", function() {{
                    window.location = "/claims/{claim.subject.id}";
                }}).addTo(map);
            """)

    rand = randint(1, 10000)
    return H.article(
        H.header(
            H.h2("Map"),
        ),
        H.div("", id=f"map{rand}", cls="map"),
        H.script(f"""
            var map = L.map('map{rand}').setView([0, 0], 1);
            L.tileLayer('{S.map_tile_url}', {{
                maxZoom: 19,
                attribution: '&copy; <a href="{S.map_tile_attribution_link}">{S.map_tile_attribution_label}</a>',
                referrerPolicy: 'origin',
            }}).addTo(map);
            """,
            *markers,
        ),
    )
