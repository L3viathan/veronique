from random import randint

from sanic import HTTPResponse

from veronique.context import context
from veronique.db import LATLON
from veronique.html import H
from veronique.settings import settings as S


def map_widget(claims):
    markers = []
    if not context.user.can("read", "verb", LATLON):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    for claim in claims:
        markers.append(f"""
            L.marker([{claim.object.value}], {{title: {str(claim.subject.html("label"))!r}}}).on("click", function() {{
                window.location = "/claims/{claim.subject.id}";
            }}).addTo(map);
        """)

    rand = randint(1, 10000)
    return H(
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
