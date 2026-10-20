import urllib.parse

from sanic import Blueprint, HTTPResponse

import veronique.objects as O
from veronique.data_types import TYPES
from veronique.html import H
from veronique.settings import settings as S
from veronique.utils import page, pagination

types = Blueprint("types", url_prefix="/types")

@types.get("/<data_type>")
async def type_request_get(request, data_type: str):
    return await TYPES[data_type].request(request, method="GET")


@types.post("/<data_type>")
async def type_request_post(request, data_type: str):
    return await TYPES[data_type].request(request, method="POST")

@types.get("/<data_type>/<value>")
@page
async def claims_with_value(request, data_type: str, value: str):
    value = urllib.parse.unquote(value)  # somehow this is not done by the framework
    if not TYPES[data_type].supports_value_query:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    page_no = int(request.args.get("page", 1))
    claims = []
    more_results = False
    if data_type == "date":
        # In dates, we use question marks to represent an unknown part. Since
        # we're going to make a LIKE query, we can replace them with
        # underscores and it should just work
        value = value.replace("?", "_")
    for i, claim in enumerate(
        O.Claim.all_with_value(
            data_type,
            value,
            page_no=page_no - 1,
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            claims.append(H.span(str(claim), cls="row"))
    return "Claims", H.article(
        H.header(
            H.h2(f"Claims of {data_type} {TYPES[data_type].display_html(value)}"),
            TYPES[data_type].value_query_extra(value) if hasattr(TYPES[data_type], "value_query_extra") else None,
        ),
        *claims,
        pagination(
            "/types/{data_type}/{value}",
            page_no,
            more_results=more_results,
        ),
    )
