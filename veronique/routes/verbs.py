from sanic import Blueprint, redirect, HTTPResponse

import veronique.objects as O
from veronique.utils import fragment, page, admin_only, pagination
from veronique.context import context
from veronique.utils import D
from veronique.data_types import TYPES
from veronique.settings import settings as S
from veronique.db import LABEL, ROOT

verbs = Blueprint("verbs", url_prefix="/verbs")


@verbs.delete("/<verb_id>")
@admin_only
@fragment
async def delete_verb(request, verb_id: int):
    O.Verb(verb_id).delete()
    return """
        <meta http-equiv="refresh" content="0; url=/">
    """


@verbs.get("/")
@page
async def list_verbs(request):
    page_no = int(request.args.get("page", 1))
    parts = []
    more_results = False
    for i, verb in enumerate(
        O.Verb.all(
            page_no=page_no - 1,
            page_size=S.page_size + 1,
        )
    ):
        if i == S.page_size:
            more_results = True
        elif verb.id not in (ROOT, LABEL):
            parts.append(f"{verb:full}")
    return "Verbs", "<br>".join(parts) + pagination(
        "/verbs",
        page_no,
        more_results=more_results,
    )


@verbs.get("/new")
@admin_only
@page
async def new_verb_form(request):
    return "New verb", f"""
        <form
            action="/verbs/new"
            method="POST"
        >
            <input name="label" placeholder="label"></input>
            <select
                name="data_type"
                hx-get="/verbs/new/steps"
                hx-target="#steps"
                hx-swap="innerHTML"
                hx-include="closest form"
            >
                <option selected disabled>--Type--</option>
                {
            "".join(
                f'''<option value="{data_type}">{data_type}</option>'''
                for data_type in TYPES
            )
        }
            </select>
            <span id="steps"></span>
        </form>
    """


@verbs.get("/new/steps")
@admin_only
@fragment
async def new_verb_form_steps(request):
    args = D(request.args)
    type = TYPES[args["data_type"]]
    if response := type.next_step(args):
        return response
    return '<button type="submit">Create</button>'


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
    parts = [f'<article><header>{verb:heading}{verb:detail}</header><div id="edit-area"></div>']
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
            parts.append(f'<span class="row">{claim:svo}</span>')
    parts.append(pagination(
        f"/verbs/{verb_id}",
        page_no,
        more_results=more_results,
    ))
    parts.append("</article>")
    return verb.label, "".join(parts)


@verbs.get("/<verb_id>/edit")
@admin_only
@fragment
async def edit_verb_form(request, verb_id: int):
    verb = O.Verb(verb_id)
    return f"""
        <form
            action="/verbs/{verb_id}/edit"
            method="POST"
        >
            <input name="label" value="{verb.label}">
            <button type="submit">»</button>
        </form>
        """


@verbs.post("/<verb_id>/edit")
@admin_only
async def edit_verb(request, verb_id: int):
    form = D(request.form)
    verb = O.Verb(verb_id)
    value = form.get("label")
    verb.rename(value)
    return redirect(f"/verbs/{verb_id}")
