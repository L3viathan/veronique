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
from veronique.html import H
from veronique.settings import settings as S
from veronique.utils import _notice, cache_pls_headers, page, pagination

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
            recent_events.append(H.hr(cls="date-today"))
        for claim in claims:
            years = re.search(r"(\d+|last|next) years?", str(claim))
            if years:
                years = 1 if years.group(1) in ("last", "next") else int(years.group(1))
            if not years or years % S.index_recent_events_mod(years) == 0:
                recent_events.append(H.span(str(claim), cls="row"))
    heading = f"Events near {'today' if page_no == 1 else f'{reference_date:%m-%d}'}"

    return H(
        H.article(
            H.header(
                H.h2(heading),
            ),
            *recent_events,
            pagination("/",
                page_no,
                more_results=True,
                allow_negative=True,
            ),
        ),
        _notice('There are <a href="/claims/comments">unresolved comments</a>') if context.user.is_admin and list(O.Claim.all_comments()) else "",
    )


def _newest_claims(request, only_entities=True):
    page_no = int(request.args.get("page", 1))
    claims = []
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
            claims.append(H.span(claim, cls="row"))
    return H.article(
        H.header(
            H.h2("Newest claims"),
        ),
        *claims,
        pagination(
            "/",
            page_no,
            more_results=more_results,
        ),
    )


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
    return H.article(
        H.header(
            H.h2(f"Véronique v{v}"),
        ),
        H.table(
            H.tr(
                H.td("Source code"),
                H.td(
                    H.a(
                        "https://github.com/L3viathan/veronique",
                        target="_blank",
                        href="https://github.com/L3viathan/veronique",
                    ),
                ),
            ),
            H.tr(
                H.td("Bug tracker"),
                H.td(
                    H.a(
                        "https://github.com/L3viathan/veronique/issues",
                        target="_blank",
                        href="https://github.com/L3viathan/veronique/issues",
                    ),
                ),
            ),
            H.tr(
                H.td("Documentation"),
                H.td(
                    H.a(
                        "https://veronique.readthedocs.io",
                        target="_blank",
                        href="https://veronique.readthedocs.io",
                    ),
                ),
            ),
            H.tr(
                H.td("Chat"),
                H.td(
                    H.a(
                        "https://discord.gg/atvuVztJcN",
                        target="_blank",
                        href="https://discord.gg/atvuVztJcN",
                    ),
                ),
            ),
            H.tr(
                H.td("Total claims"),
                H.td(str(stats["total"])),
            ),
            H.tr(
                H.td("Entities"),
                H.td(str(stats["verbs"][ROOT])),
            ),
            H.tr(
                H.td("Categories"),
                H.td(
                    ', '.join(f"{O.Claim(category)} ({count})" for category, count in stats["categories"].items()),
                ),
            ),
            H.tr(
                H.td("Verbs"),
                H.td(str(n_verbs)),
            ),
            H.tr(
                H.td("Users"),
                H.td(str(n_users)),
            ),
            id="about-table",
            cls="striped",
        ),
    )

@index.get("/user-content/<identifier>/<filename>")
async def get_user_content(request, identifier, filename):
    # no security for this — identifier is randomly generated and assumed unguessable
    return await file_stream(
        TYPES["file"].FILE_PATH / identifier,
        filename=filename,
        headers=cache_pls_headers(),
    )
