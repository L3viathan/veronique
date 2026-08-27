import functools
import re
from datetime import date, timedelta
from importlib.metadata import PackageNotFoundError, version

from sanic import Blueprint
from sanic.response import file_stream

import veronique.objects as O
from veronique.context import context
from veronique.data_types import TYPES
from veronique.db import ROOT
from veronique.settings import settings as S
from veronique.utils import _notice, page, pagination

index = Blueprint("index")


def _recent_events_page(request, include_validity=False):
    recent_events = []
    page_no = int(request.args.get("page", 1))
    reference_date = date.today()
    if page_no != 1:
        reference_date += timedelta(days=(S.index_days_back+S.index_days_ahead+1)*(page_no-1))
    target_days = [
        f"{reference_date + timedelta(days=d):%m-%d}"
        for d in range(-S.index_days_back, S.index_days_ahead+1)
    ]
    for d, claims in O.Claim.all_at_dates(target_days, include_validity=include_validity):
        if d == f"{reference_date:%m-%d}" and not claims:
            recent_events.append('<hr class="date-today">')
        for claim in claims:
            years = re.search(r"(\d+|last|next) years?", str(claim))
            if years:
                years = 1 if years.group(1) in ("last", "next") else int(years.group(1))
            if not years or years % S.index_recent_events_mod(years) == 0:
                recent_events.append(f'<span class="row">{claim}</span>')
    heading = f"Events near {'today' if page_no == 1 else f'{reference_date:%m-%d}'}"
    return f"""
        <article><header>
        <h2>{heading}</h2>
        </header>
        {"".join(recent_events)}
        {pagination("/",
            page_no,
            more_results=True,
            allow_negative=True,
        )}
        </article>
        {_notice('There are <a href="/claims/comments">unresolved comments</a>') if context.user.is_admin and list(O.Claim.all_comments()) else ""}
    """


def _newest_claims(request, only_entities=True):
    page_no = int(request.args.get("page", 1))
    parts = ["<article><header><h2>Newest claims</h2></header>"]
    more_results = False
    for i, claim in enumerate(O.Claim.all(
        verb_id=ROOT if only_entities else None,
        order_by="created_at DESC",
        page_no=page_no - 1,
        page_size=S.page_size + 1,
    )):
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f'<span class="row">{claim}</span>')
    parts.append(pagination(
        "/",
        page_no,
        more_results=more_results,
    ))
    parts.append("</article>")
    return "".join(parts)


@index.get("/")
@page
async def homepage(request):
    return {
        "recent_events": _recent_events_page,
        "all_recent_events": functools.partial(_recent_events_page, include_validity=True),
        "newest_claims": functools.partial(_newest_claims, only_entities=False),
        "newest_entities": _newest_claims,
    }[S.index_type](request)


@index.get("/about")
@page
async def about(request):
    stats = O.Claim.stats()
    n_users = len(list(O.User.all()))
    n_verbs = len(list(O.Verb.all()))
    try:
        v = version("veronique")
    except PackageNotFoundError:
        v = "?.?.? (local Git checkout)"
    return f"""
    <article>
    <header><h2>Véronique v{v}<h2></header>
    <table id="about-table" class="striped">
        <tr><td>Source code</td><td><a target="_blank" href="https://github.com/L3viathan/veronique">https://github.com/L3viathan/veronique</a></td></tr>
        <tr><td>Bug tracker</td><td><a target="_blank" href="https://github.com/L3viathan/veronique/issues">https://github.com/L3viathan/veronique/issues</a></td></tr>
        <tr><td>Documentation</td><td><a target="_blank" href="https://veronique.readthedocs.io">https://veronique.readthedocs.io</a></td></tr>
        <tr><td>Chat</td><td><a target="_blank" href="https://discord.gg/atvuVztJcN">https://discord.gg/atvuVztJcN</a></td></tr>
        <tr><td>Total claims</td><td>{stats["total"]}</td></tr>
        <tr><td>Entities</td><td>{stats["verbs"][ROOT]}</td></tr>
        <tr><td>Categories</td><td>{', '.join(f"{O.Claim(category)} ({count})" for category, count in stats["categories"].items())}</td></tr>
        <tr><td>Verbs</td><td>{n_verbs}</td></tr>
        <tr><td>Users</td><td>{n_users}</td></tr>
    </table>
    </article>
    """

@index.get("/user-content/<identifier>")
async def get_user_content(request, identifier):
    # no security for this — identifier is randomly generated and assumed unguessable
    return await file_stream(TYPES["file"].FILE_PATH / identifier)
