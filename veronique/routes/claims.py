import base64
from collections import defaultdict
from math import log

from sanic import Blueprint, HTTPResponse, raw, redirect

import veronique.objects as O
from veronique.context import context
from veronique.data_types import TYPES
from veronique.db import AVATAR, COMMENT, IS_A, ROOT
from veronique.html import H
from veronique.network import network_widget
from veronique.settings import settings as S
from veronique.utils import D, cache_pls_headers, fragment, page, pagination

claims = Blueprint("claims", url_prefix="/claims")


@claims.get("/new-entity")
@page
async def new_entity_form(request):
    if not context.user.can("write", "verb", ROOT):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    categories = O.Claim.all_categories()
    args = D(request.args)
    connect_info = ""
    if connect := args.get("connect"):
        conn_claim_id, conn_dir, conn_verb_id = connect.split(":")
        if context.user.can("write", "verb", int(conn_verb_id)):
            conn_verb = O.Verb(int(conn_verb_id))
            conn_claim = O.Claim(int(conn_claim_id))
            connect_info = H(
                H.p(f"After creation, an {conn_dir} {conn_verb} link will be made to {conn_claim}."),
                H.input(type="hidden", name="connect", value=connect),
            )
    name = args.get("name", "")
    return "New entity", H.article(
        H.header(H.h2("New entity")),
        H.form(
            H.input(name="name", placeholder="name", value=name),
            H.select(
                H.option("(None)", value=""),
                *(H.option(cat.html("label"), value=str(cat.id), selected=i==0) for i, cat in enumerate(categories)),
                name="category",
            ),
            connect_info,
            H.button("»", type="submit"),
            action="/claims/new-entity",
            method="POST",
        ),
    )


@claims.post("/new-entity")
async def new_entity(request):
    form = D(request.form)
    name = form["name"]
    if not context.user.can("write", "verb", ROOT):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    claim = O.Claim.new_entity(name)
    if form.get("category") and context.user.can("write", "verb", IS_A):
        cat = O.Claim(int(form["category"]))
        O.Claim.new(claim, O.Verb(IS_A), cat)
    if connect := form.get("connect"):
        conn_claim_id, conn_dir, conn_verb_id = connect.split(":")
        if context.user.can("write", "verb", int(conn_verb_id)):
            conn_verb = O.Verb(int(conn_verb_id))
            conn_claim = O.Claim(int(conn_claim_id))
            if conn_dir == "incoming":
                O.Claim.new(claim, conn_verb, conn_claim)
            else:
                O.Claim.new(conn_claim, conn_verb, claim)
            # We came from the conn_claim, so we want to go back there.
            return redirect(f"/claims/{conn_claim.id}")
        # If we couldn't make the link, we want to go to the new entity instead.
    return redirect(f"/claims/{claim.id}")


@claims.get("/new/<claim_ids>/<direction:incoming|outgoing>")
@fragment
async def new_claim_form(request, claim_ids: list[int], direction: str):
    if isinstance(claim_ids, list):
        claim_ids = ",".join(claim_ids)
    verbs = O.Verb.all(
        page_size=9999, data_type="directed_link" if direction == "incoming" else None, only_writable=True
    )
    return H.form(
        H.select(
            H.option("--Verb--", selected=True, disabled=True),
            *(
                H.option(f"{verb.label} ({verb.data_type})", value=str(verb.id))
                for verb in verbs
                if verb.id >= 0 and verb.data_type is not TYPES["inferred"]
            ),
            name="verb",
            hx_get=f"/claims/new/verb?claim_ids={claim_ids}&direction={direction}",
            hx_target="#valueinput",
            hx_swap="innerMorph",
        ),
        H.span("", id="valueinput"),
        action=f"/claims/new/{claim_ids}/{direction}",
        method="POST",
        enctype="multipart/form-data",
    )


@claims.get("/new/verb")
@fragment
async def new_claim_form_verb_input(request):
    args = D(request.args)
    if not context.user.can("write", "verb", int(args["verb"])):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verb = O.Verb(int(args["verb"]))
    if args.get("standalone"):
        return H.form(
            H.input(type="hidden", name="verb", value=str(verb.id)),
            verb.data_type.input_html(
                claim_ids=args.get("claim_ids"),
                direction=args.get("direction"),
                verb_id=verb.id,
            ),
            H.button("»", type="submit"),
            action=f'/claims/new/{args.get("claim_ids")}/{args.get("direction")}',
            method="POST",
            enctype="multipart/form-data",
        )
    else:
        return H(
            verb.data_type.input_html(
                claim_ids=args.get("claim_ids"),
                direction=args.get("direction"),
                verb_id=verb.id,
            ),
            H.button("»", type="submit"),
        )


@claims.post("/new/<claim_ids>/<direction:incoming|outgoing>")
async def new_claims(request, claim_ids: list[int], direction: str):
    for claim_id in claim_ids.split(","):
        claim = O.Claim(int(claim_id))
        form = D(request.form)
        if not (
            context.user.can("read", "verb", claim.verb.id)
            and context.user.can("write", "verb", int(form["verb"]))
        ):
            return HTTPResponse(
                body="403 Forbidden",
                status=403,
            )
        if "value" in request.files:
            f = request.files["value"][0]
            form["value"] = f
        verb = O.Verb(int(form["verb"]))
        value = form.get("value")
        if verb.data_type.name.endswith("directed_link"):
            value = O.Claim(int(value))
            if not context.user.can("read", "verb", value.verb.id):
                return HTTPResponse(
                    body="403 Forbidden",
                    status=403,
                )
        elif verb.data_type.name == "inferred":
            return HTTPResponse(
                body="400 Bad Request",
                status=400,
            )
        else:
            try:
                value = O.Plain.from_form(verb, form)
            except ValueError:
                return redirect(f"/claims/{claim_id}")
        if direction == "incoming":
            O.Claim.new(value, verb, claim)
        else:
            O.Claim.new(claim, verb, value)
    return redirect(f"/claims/{claim_id}")


@claims.get("/<claim_id>/edit")
@fragment
async def edit_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    return H.form(
        claim.verb.data_type.input_html(value=claim.object, verb_id=claim.verb.id),
        H.button("»", type="submit"),
        action=f"/claims/{claim_id}/edit",
        method="POST",
        enctype="multipart/form-data",
    )


@claims.get("/<claim_id>/move")
@fragment
async def move_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    return H.form(
        TYPES["directed_link"].input_html(value=claim.object, allow_connect=False),
        H.button("»", type="submit"),
        action=f"/claims/{claim_id}/move",
        method="POST",
    )


@claims.get("/<claim_id>/reverb")
@fragment
async def reverb_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verbs = O.Verb.all(page_size=9999)
    verbs = [
        H.option(v.html(), f" ({v.data_type})", value=str(v.id), selected=v.id==claim.verb.id)
        for v in verbs
        if v.id >= 0 and claim.verb.can_turn_into(v) and context.user.can("write", "verb", v.id)
    ]
    return H.form(
        H.select(
            *verbs,
            name="verb",
        ),
        H.button("»", type="submit"),
        action=f"/claims/{claim_id}/reverb",
        method="POST",
    )


@claims.delete("/<claim_id>")
@fragment
async def delete_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    if claim.subject:
        redirect = f"/claims/{claim.subject.id}"
    else:
        redirect = "/"

    claim.delete()
    return H.meta(http_equiv="refresh", content=f"0; url={redirect}")


@claims.post("/<claim_id>/edit")
async def edit_claim(request, claim_id: int):
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    value = form.get("value")
    if claim.verb.data_type.name.endswith("directed_link"):
        value = O.Claim(int(value))
    else:
        value = O.Plain.from_form(claim.verb, form)
    claim.set_value(value)
    return redirect(f"/claims/{claim_id}")


@claims.post("/<claim_id>/reverb")
async def reverb_claim(request, claim_id: int):
    form = D(request.form)
    claim = O.Claim(claim_id)
    verb_id = int(form.get("verb"))
    if not context.user.is_admin and (claim.owner.id != context.user.id or not context.user.can("write", "verb", verb_id)):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    claim.set_verb(O.Verb(verb_id))
    return redirect(f"/claims/{claim_id}")


@claims.post("/<claim_id>/move")
async def move_claim(request, claim_id: int):
    form = D(request.form)
    claim = O.Claim(claim_id)
    if claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    value = form.get("value")
    claim.set_subject(O.Claim(int(value)))
    return redirect(f"/claims/{claim_id}")


@claims.get("/")
@page
async def list_labelled_claims(request):
    page_no = int(request.args.get("page", 1))
    claims = []
    more_results = False
    for i, claim in enumerate(
        O.Claim.all_labelled(
            order_by="id DESC",
            page_no=page_no - 1,
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            claims.append(H.span(str(claim), cls="row"))
    return "Claims", H.article(
        *claims,
        pagination(
            "/claims",
            page_no,
            more_results=more_results,
        ),
    )


@claims.get("/network")
@page
async def view_network(request):
    claims = (
        c
        for c in O.Claim.all_labelled(page_size=9999)
    )
    return "Network", network_widget(claims)


@claims.get("/<claim_id>/network")
@page
async def view_claim_network(request, claim_id: int):
    claim = O.Claim(claim_id)
    claims = [claim]
    claims.extend(incoming.subject for incoming in claim.incoming_claims(page_size=999))
    for outgoing in claim.outgoing_claims(page_size=999):
        if outgoing.verb.data_type in (TYPES["directed_link"], TYPES["undirected_link"]) and outgoing.verb.id != IS_A:
            if outgoing.object != claim:
                claims.append(outgoing.object)
            else:
                claims.append(outgoing.subject)
    colormap = defaultdict(lambda: 1)
    colormap[claim_id] = 2
    return claim.html("label"), H.article(
        H.header(claim.html("handle"), claim.html("heading")),
        network_widget(claims, links_go_to="network", colormap=colormap, freeze_after=log(len(claims))),
        cls="network",
    )


@claims.get("/<claim_id>")
@page
async def view_claim(request, claim_id: int):
    page_no = int(request.args.get("page", 1))
    claim = O.Claim(claim_id)
    if not context.user.can("read", "verb", claim.verb.id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    incoming_mentions = list(claim.incoming_mentions(
        page_no=page_no - 1,
        page_size=S.page_size + 1,  # so we know if there would be more results
    ))
    comments = list(claim.comments(
        page_no=page_no - 1,
        page_size=S.page_size + 1,  # so we know if there would be more results
    ))
    incoming_claims = list(claim.incoming_claims(
        page_no=page_no - 1,
        page_size=S.page_size + 1,  # so we know if there would be more results
    ))
    outgoing_claims = list(claim.outgoing_claims(
        page_no=page_no - 1,
        page_size=S.page_size + 1,  # so we know if there would be more results
    ))
    if any(len(c) > S.page_size for c in (incoming_mentions, comments, incoming_claims, outgoing_claims)):
        more_results = True
    else:
        more_results = False
    return claim.html("label"), H.article(
        H.header(
            claim.html("heading"),
            claim.html("avatar") if claim.is_entity else None,
            claim.html("hamburger"),
        ),
        H.div("", id="edit-area"),
        H.table(
            H.tr(
                H.td(
                    H.div(
                        "+",
                        hx_swap="outerMorph",
                        hx_get=f"/claims/new/{claim_id}/incoming",
                        cls="new-item-placeholder",
                    ) if context.user.is_admin or context.user.writable_verbs else None
                ),
                H.td(
                    H.div(
                        "+",
                        hx_swap="outerMorph",
                        hx_get=f"/claims/new/{claim_id}/outgoing",
                        cls="new-item-placeholder",
                    ) if context.user.is_admin or context.user.writable_verbs else None
                ),
                cls="placeholders",
            ),
            H.tr(
                H.td(
                    *(H.span(c.html("sv"), cls="row") for c in incoming_claims),
                ),
                H.td(
                    *(H.span(c.html(f"vo:{claim_id}"), cls="row") for c in outgoing_claims if c.verb.id not in (IS_A, AVATAR, COMMENT)),
                    *(H.span(c.html(f"vo:{claim_id}"), cls="row") for c in claim.outgoing_inferred_claims()),
                ),
                cls="claims",
            ),
            cls="claims",
        ),
        H.hr(),
        H(
            H.h3("Mentions"),
            *(H.span(str(c), cls="row") for c in incoming_mentions)
        ) if incoming_mentions else None,
        H.footer(
            H(
                H.table(
                    *(c.html("comment") for c in comments),
                    cls="comments",
                ),
            ) if comments else None,
            H.form(
                H.input(type="hidden", name="verb", value=str(COMMENT)),
                H.input(name="value", placeholder="Add comment..."),
                H.input(type="submit", hidden=True),
                method="POST",
                action=f"/claims/new/{claim_id}/outgoing",
            ) if context.user.can("write", "verb", COMMENT) else None,
            H.small(
                f"Created at: {claim.created_at}",
                f", updated at: {claim.updated_at}" if claim.updated_at != claim.created_at else None,
                f", by {claim.owner}" if claim.owner else None,
                cls="dim",
            ),
        ),
        pagination(
            f"/claims/{claim_id}",
            page_no,
            more_results=more_results,
        )
    )


@claims.get("/<claim_id>/avatar")
@page
async def view_claim_avatar(request, claim_id: int):
    claim = O.Claim(claim_id)
    data = claim.get_data()
    if AVATAR not in data or context.user.redact:
        # transparent pixel
        value = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        mime = "image/png"
        updated_at = claim.updated_at
    else:
        avatar_claim = data[AVATAR][0]
        value = avatar_claim.object.value
        mime = value[value.index(":"):value.index(";")]
        value = base64.b64decode(value[value.index(","):])
        updated_at = avatar_claim.updated_at or avatar_claim.created_at

    return raw(
        value,
        content_type=mime,
        headers=cache_pls_headers(updated_at),
    )


@claims.get("/comments")
@page
async def list_comments(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, claim in enumerate(
        O.Claim.all_comments(
            order_by="id DESC",
            page_no=page_no - 1,
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
    ):
        if i:
            parts.append(H.br())
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f"{claim}")
    return "Comments", H(
        *parts,
        pagination(
            "/claims/comments",
            page_no,
            more_results=more_results,
        ),
    )
