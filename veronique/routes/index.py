import functools
from datetime import date, timedelta

from sanic import Blueprint

import veronique.objects as O
from veronique.settings import settings as S
from veronique.context import context
from veronique.utils import page, coalesce, pagination, _notice
from veronique.nomnidate import NonOmniscientDate
from veronique.db import ROOT


index = Blueprint("index")


def _recent_events_page(request):
    recent_events = []
    page_no = int(request.args.get("page", 1))
    past_today = False
    reference_date = date.today()
    if page_no != 1:
        reference_date += timedelta(days=(S.index_days_back+S.index_days_ahead+1)*(page_no-1))
    for claim in sorted(
        O.Claim.all_near_today(reference_date, days_back=S.index_days_back, days_ahead=S.index_days_ahead),
        key=lambda c: (
            # unspecified dates are always before everything else
            coalesce((reference_date - NonOmniscientDate(c.object.value)).days, 99)
        ),
        reverse=True,
    ):
        difference = coalesce(
            (reference_date - NonOmniscientDate(claim.object.value)).days,
            99,
        )
        if difference == 0:
            past_today = True
        elif not past_today and (difference or 0) < 0 and page_no == 1:
            recent_events.append('<hr class="date-today">')
            past_today = True
        recent_events.append(f'<span class="row">{claim:link}</span>')
    if page_no == 1 and not past_today:
        recent_events.append('<hr class="date-today">')
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


def _newest_claims(request, only_root=True):
    page_no = int(request.args.get("page", 1))
    parts = ["<article><header><h2>Newest claims</h2></header>"]
    more_results = False
    for i, claim in enumerate(O.Claim.all(
        verb_id=ROOT if only_root else None,
        order_by="created_at DESC",
        page_no=page_no - 1,
        page_size=S.page_size + 1,
    )):
        if i == S.page_size:
            more_results = True
        else:
            parts.append(f'<span class="row">{claim:link}</span>')
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
        "newest_claims": functools.partial(_newest_claims, only_root=False),
        "newest_root_claims": _newest_claims,
    }[S.index_type](request)
