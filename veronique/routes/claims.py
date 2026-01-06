import base64

from sanic import Blueprint, HTTPResponse, redirect, raw

import veronique.objects as O
from veronique.utils import fragment, page, pagination, D
from veronique.data_types import TYPES
from veronique.settings import settings as S
from veronique.context import context
from veronique.db import IS_A, ROOT, AVATAR, COMMENT

claims = Blueprint("claims", url_prefix="/claims")


@claims.get("/autocomplete")
@fragment
async def autocomplete_claims(request):
    args = D(request.args)
    query = args.get("ac-query", "")
    connect = args.get("connect", None)
    if not query:
        return ""
    claims = O.Claim.search(
        q=query,
        page_size=5,
    )
    return f"""
    {"".join(f"{claim:ac-result}" for claim in claims if context.user.can("read", "verb", claim.verb.id))}
    {f'''<a class="clickable" href="/claims/new-root?connect={connect}&name={query}">
        <em>Create</em> {query} <em> claim...</em>
    </a>''' if connect is not None else ''}
    """


@claims.get("/autocomplete/accept/<claim_id>")
@fragment
async def autocomplete_claims_accept(request, claim_id: int):
    claim = O.Claim(claim_id)
    return f"""
        <input
            name="ac-query"
            placeholder="Start typing..."
            hx-get="/claims/autocomplete?claim={claim_id}"
            hx-target="next .ac-results"
            hx-swap="innerHTML"
            hx-trigger="input changed delay:200ms, search"
            value="{claim:label}"
        >
        <input type="hidden" name="value" value="{claim.id}"
        <div class="ac-results">
        </div>
    """


@claims.get("/new-root")
@page
async def new_root_claim_form(request):
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
            connect_info = f"""
            <p>After creation, an {conn_dir} {conn_verb:link} link will be made to {conn_claim:link}.</p>
            <input type="hidden" name="connect" value="{connect}">
            """
    name = args.get("name", "")
    return "New root", f"""
    <article>
    <header><h2>New root claim</h2></header>
        <form action="/claims/new-root" method="POST">
            <input name="name" placeholder="name" value="{name}"></input>
            <select
                name="category"
            >
                <option value="">(None)</option>
                {
            "".join(
                f'''<option
                            value="{cat.id}"
                            {'selected="selected"' if i == 0 else ""}
                        >{cat:label}</option>'''
                for i, cat in enumerate(categories)
            )
        }
            </select>
            {connect_info}
            <button type="submit">»</button>
        </form>
    </article>
    """


@claims.post("/new-root")
async def new_root_claim(request):
    form = D(request.form)
    name = form["name"]
    if not context.user.can("write", "verb", ROOT):
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    claim = O.Claim.new_root(name)
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
        # If we couldn't make the link, we want to go to the new root instead.
    return redirect(f"/claims/{claim.id}")


@claims.get("/new/<claim_id>/<direction:incoming|outgoing>")
@fragment
async def new_claim_form(request, claim_id: int, direction: str):
    verbs = O.Verb.all(
        page_size=9999, data_type="directed_link" if direction == "incoming" else None, only_writable=True
    )
    return f"""
        <form
            action="/claims/new/{claim_id}/{direction}"
            method="POST"
            enctype="multipart/form-data"
        >
            <select
                name="verb"
                hx-get="/claims/new/verb?claim_id={claim_id}&direction={direction}"
                hx-target="#valueinput"
                hx-swap="innerHTML"
            >
                <option selected disabled>--Verb--</option>
                {
                    "".join(
                        f'''<option
                                        value="{verb.id}"
                                    >{verb.label} ({verb.data_type})</option>'''
                        for verb in verbs
                        if verb.id != ROOT and verb.data_type is not TYPES["inferred"]
                    )
                }
            </select>
            <span id="valueinput"></span>
        </form>
    """


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
    return f"""
        {verb.data_type.input_html(claim_id=args.get("claim_id"), direction=args.get("direction"), verb_id=verb.id)}
        <button type="submit">»</button>
        """


@claims.post("/new/<claim_id>/<direction:incoming|outgoing>")
async def new_claim(request, claim_id: int, direction: str):
    claim = O.Claim(claim_id)
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
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
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
    return f"""
        <form
            action="/claims/{claim_id}/edit"
            method="POST"
        >
            {claim.verb.data_type.input_html(value=claim.object)}
            <button type="submit">»</button>
        </form>
        """


@claims.get("/<claim_id>/move")
@fragment
async def move_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    return f"""
        <form
            action="/claims/{claim_id}/move"
            method="POST"
        >
            {TYPES["directed_link"].input_html(value=claim.object, allow_connect=False)}
            <button type="submit">»</button>
        </form>
        """


@claims.get("/<claim_id>/reverb")
@fragment
async def reverb_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verbs = O.Verb.all(data_type=claim.verb.data_type.name)
    parts = [
        f"""
        <form
            action="/claims/{claim_id}/reverb"
            method="POST"
        >
            <select name="verb">
        """
    ]
    for verb in verbs:
        parts.append(f"""
            <option value="{verb.id}" {"selected" if verb.id == claim.verb.id else ""}>{verb}</option>
        """)
    parts.append(
        """
            </select>
            <button type="submit">»</button>
        </form>
        """
    )
    return "".join(parts)


@claims.delete("/<claim_id>")
@fragment
async def delete_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    subject_id = claim.subject.id
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    claim.delete()
    return f"""
        <meta http-equiv="refresh" content="0; url=/claims/{subject_id}">
    """


@claims.post("/<claim_id>/edit")
async def edit_claim(request, claim_id: int):
    form = D(request.form)
    if "value" in request.files:
        f = request.files["value"][0]
        form["value"] = f"data:{f.type};base64,{base64.b64encode(f.body).decode()}"
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
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    verb_id = int(form.get("verb"))
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
    parts = ["<article>"]
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
            parts.append(f'<span class="row">{claim:link}</span>')
    parts.append(pagination(
        "/claims",
        page_no,
        more_results=more_results,
    ))
    parts.append("</article>")
    return "Claims", "".join(parts)


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
    return f"{claim:label}", f"""
        <article>
            <header>{claim:heading}{claim:avatar}</header>
            <div id="edit-area"></div>
            <table class="claims"><tr><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/incoming" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        {"".join(f'<span class="row">{c:sv}</span>' for c in incoming_claims)}
        </td><td>
        {
            f'<div hx-swap="outerHTML" hx-get="/claims/new/{claim_id}/outgoing" class="new-item-placeholder">+</div>'
            if context.user.is_admin or context.user.writable_verbs
            else ""
        }
        {"".join(f'<span class="row">{c:vo:{claim_id}}</span>' for c in outgoing_claims if c.verb.id not in (IS_A, AVATAR, COMMENT))}
        {"".join(f'<span class="row">{c:vo:{claim_id}}</span>' for c in claim.outgoing_inferred_claims())}
        </td></tr></table>
        {"<hr><h3>Mentions</h3>" + "".join(f'<span class="row">{c:svo}</span>' for c in incoming_mentions) if incoming_mentions else ""}
        <footer>
        {'<table class="comments">' + "".join(f"{c:comment}" for c in comments) + "</table>" if comments else ""}
        {
        f'''<form method="POST" action="/claims/new/{claim_id}/outgoing">
            <input type="hidden" name="verb" value="{COMMENT}">
            <input name="value" placeholder="Add comment...">
            <input type="submit" hidden>
        </form>''' if context.user.can("write", "verb", COMMENT) else ""
        }
        </footer>
        {pagination(
            f"/claims/{claim_id}",
            page_no,
            more_results=more_results,
        )}
        </article>
    """


@claims.get("/<claim_id>/avatar")
@page
async def view_claim_avatar(request, claim_id: int):
    claim = O.Claim(claim_id)
    data = claim.get_data()
    if AVATAR not in data or context.user.redact:
        # black pixel
        value = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AWNgAAAAAgABc3UBGAAAAABJRU5ErkJggg==")
    else:
        value = data[AVATAR][0].object.value
        mime = value[value.index(":"):value.index(";")]
        value = base64.b64decode(value[value.index(","):])

    return raw(value, content_type=mime)


@claims.get("/<claim_id>/rename")
@fragment
async def rename_root_claim_form(request, claim_id: int):
    claim = O.Claim(claim_id)
    return f"""
        <form method="POST" action="/claims/{claim_id}/rename">
        <fieldset role="group">
            <input name="value" value="{claim.object.value}">
            <input type="submit" value="›">
        </fieldset>
        </form>
    """


@claims.post("/<claim_id>/rename")
@fragment
async def rename_root_claim(request, claim_id: int):
    claim = O.Claim(claim_id)
    if not context.user.is_admin and claim.owner.id != context.user.id:
        return HTTPResponse(
            body="403 Forbidden",
            status=403,
        )
    if claim.verb.id != ROOT:
        return HTTPResponse(
            body="400 Bad Request",
            status=400,
        )
    value = O.Plain.from_form(claim.verb, request.form)
    claim.set_value(value)
    return redirect(f"/claims/{claim.id}")


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
            parts.append("<br>")
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f"{claim:link}")
    return "Comments", "".join(parts) + pagination(
        "/claims/comments",
        page_no,
        more_results=more_results,
    )
