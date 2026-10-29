from sanic import Blueprint, HTTPResponse, redirect

import veronique.objects as O
from veronique.context import context
from veronique.data_types import TYPES
from veronique.db import ROOT
from veronique.html import H
from veronique.settings import settings as S
from veronique.utils import D, admin_only, fragment, page, pagination

verbs = Blueprint("verbs", url_prefix="/verbs")


@verbs.delete("/<verb_id>")
@admin_only
@fragment
async def delete_verb(request, verb_id: int):
    O.Verb(verb_id).delete()
    return H.meta(http_equiv="refresh", content="0; url=/")


@verbs.get("/")
@page
async def list_verbs(request):
    page_no = int(request.args.get("page", 1))
    verbs = []
    more_results = False
    for i, verb in enumerate(
        O.Verb.all(
            page_no=page_no - 1,
            page_size=S.page_size + 1,
        )
    ):
        if i == S.page_size:
            more_results = True
        elif verb.id != ROOT:
            verbs.append(H.span(verb.html("full"), cls="row"))
    return "Verbs", H.article(
        *verbs,
        pagination(
            "/verbs",
            page_no,
            more_results=more_results,
        ),
    )


@verbs.get("/new")
@admin_only
@page
async def new_verb_form(request):
    return "New verb", H.article(
        H.header(H.h2("New verb")),
        H.form(
            H.input(name="label", placeholder="label"),
            H.select(
                H.option("--Type--", selected=True, disabled=True),
                *(H.option(data_type, value=data_type) for data_type in TYPES),
                name="data_type",
                hx_get="/verbs/new/steps",
                hx_target="#steps",
                hx_swap="innerMorph",
                hx_include="closest form",
            ),
            H.span("", id="steps"),
            action="/verbs/new",
            method="POST",
        ),
    )


@verbs.get("/new/steps")
@admin_only
@fragment
async def new_verb_form_steps(request):
    args = D(request.args)
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return H.button("Create", type="submit")


@verbs.post("/new")
@admin_only
async def new_verb(request):
    form = D(request.form)
    data_type = TYPES[form["data_type"]]
    extra = data_type.get_extra(form)
    verb = O.Verb.new(
        form["label"],
        data_type=data_type,
        extra=extra,
    )
    return redirect(f"/verbs/{verb.id}")


@verbs.get("/<verb_id>")
@page
async def view_verb(request, verb_id: int):
    page_no = int(request.args.get("page", 1))
    if not context.user.can("read", "verb", verb_id):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verb = O.Verb(verb_id)
    claims = []
    more_results = False
    for i, claim in enumerate(
        verb.claims(
            page_no=page_no - 1,
            page_size=S.page_size + 1,  # so we know if there would be more results
        )
    ):
        if i == S.page_size:
            more_results = True
        else:
            claims.append(H.span(str(claim), cls="row"))
    return verb.label, H.article(
        H.header(
            verb.html("heading"),
            verb.html("hamburger"),
            verb.html("detail"),
        ),
        H.div("", id="edit-area"),
        *claims,
        pagination(
            f"/verbs/{verb_id}",
            page_no,
            more_results=more_results,
        ),
    )


@verbs.get("/<verb_id>/edit")
@admin_only
@fragment
async def edit_verb_form(request, verb_id: int):
    verb = O.Verb(verb_id)
    return H.form(
        H.input(name="label", value=verb.label),
        verb.html("edit"),
        H.button("\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}", type="submit"),
        action=f"/verbs/{verb_id}/edit",
        method="POST",
    )


@verbs.post("/<verb_id>/edit")
@admin_only
async def edit_verb(request, verb_id: int):
    form = D(request.form)
    verb = O.Verb(verb_id)
    value = form.pop("label")
    verb.rename(value)
    verb.edit(form)
    return redirect(f"/verbs/{verb_id}")
