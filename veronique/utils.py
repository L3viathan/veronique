import functools
import re
from datetime import datetime
from time import monotonic
from types import CoroutineType

from sanic import HTTPResponse, html

from veronique.context import context
from veronique.db import ROOT
from veronique.html import H, Tag
from veronique.settings import settings as S
from veronique.templates import TEMPLATE

startup_time = datetime.now()

def _error(msg):
    return H.aside(
        H.strong("Error:"),
        " ",
        msg,
        " ",
        H.span(
            "\N{MULTIPLICATION SIGN}",
            hx_get="about:blank",
            hx_on__click="document.getElementById('errors').remove()",
            cls="dismiss",
        ),
        id="errors",
    )


def _notice(msg):
    return H.aside(
        H.strong("Info:"),
        " ",
        msg,
        " ",
        H.span(
            "\N{MULTIPLICATION SIGN}",
            hx_get="about:blank",
            hx_on__click="document.getElementById('notices').remove()",
            cls="dismiss",
        ),
        id="notices",
    )


def D(multival_dict):
    return {key: val[0] for key, val in multival_dict.items()}


def mobile(mob, nomob):
    return f"""<span class="mobile-only">{mob}</span><span class="no-mobile">{nomob}</span>"""


def pagination(url, page_no, *, more_results=True, allow_negative=False):
    if page_no == 1 and not more_results:
        return ""
    q = "&" if "?" in url else "?"
    if "page=" in url or "page=" in url:
        url_template = re.sub(r"page=\d+", "page={}", url)
    else:
        url_template = f"{url}{q}page={{}}"
    return H.footer(
        H.a(
            "&lt;",
            role="button",
            cls="prev",
            href=url_template.format(page_no - 1),
            disabled=page_no==1 and not allow_negative,
        ),
        H.a(
            "&gt;",
            role="button",
            cls="next",
            href=url_template.format(page_no + 1),
            disabled=not more_results,
        ),
    )


def fragment(fn):
    """Mark an endpoint as returning HTML, but not a full page."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ret = fn(*args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, HTTPResponse):
            return ret
        if isinstance(ret, Tag):
            ret = str(ret)
        return html(ret)

    return wrapper


def page(fn):
    """Mark an endpoint as returning a full standalone page."""

    @functools.wraps(fn)
    async def wrapper(request, *args, **kwargs):
        ret = fn(request, *args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, HTTPResponse):
            return ret
        elif isinstance(ret, Tag):
            title = S.app_name
        else:
            title, ret = ret
            title = f"{title} — {S.app_name}"

        gotos = []
        for page_name, path, restricted in [
            ("Claims", "claims", False),
            ("Network", "claims/network", False),
            ("Map", "claims/map", False),
            ("Verbs", "verbs", False),
            ("Queries", "queries", False),
            ("Users", "users", True),
            ("Tools: Connections", "tools/connections", False),
            ("Tools: Merge", "tools/merge", True),
        ]:
            if restricted and not context.user.is_admin:
                gotos.append(H.li(H.a(page_name, href="#", disabled=True)))
            else:
                gotos.append(H.li(H.a(page_name, href=f"/{path}")))
        news = H.li(
            H.details(
                H.summary(mobile("New", "New...")),
                H.ul(
                    H.li(H.a("Entity", href="/claims/new-entity", disabled=not context.user.can("write", "verb", ROOT))),
                    H.li(H.a("Verb", href="/verbs/new", disabled=not context.user.is_admin)),
                    H.li(H.a("Query", href="/queries/new", disabled=not context.user.is_admin)),
                    H.li(H.a("User", href="/users/new", disabled=not context.user.is_admin)),
                    H.li(H.a("Bulk claim", href="/tools/bulk-claim", disabled=not context.user.is_admin)),
                    dir="rtl",
                ),
                cls="dropdown",
            )
        )
        user_emoji = "\N{BUST IN SILHOUETTE}\N{VARIATION SELECTOR-15}"
        user = H.li(
            H.details(
                H.summary(mobile(user_emoji, context.user.html("label"))),
                H.ul(
                    H.li(
                        H.a("Stop impersonating", href="#", hx_post="/users/stop-impersonating"),
                    ) if context.impersonator else None,
                    H.li(
                        H.a("Settings", href="/settings"),
                    ),
                    H.li(
                        H.a("Help", target="_blank", href="https://veronique.readthedocs.io"),
                    ),
                    H.li(
                        H.a("About", href="/about"),
                    ),
                    H.li(
                        H.a("Logout", href="/logout"),
                    ),
                    dir="rtl",
                ),
                cls="dropdown",
            ),
        )
        return html(
            str(TEMPLATE(
                title=title,
                content=ret,
                gotos=gotos,
                news=news,
                user=user,
                errors=_error(request.args["err"][0]) if "err" in request.args else None,
            ))
        )

    return wrapper


def coalesce(*values):
    """Like SQL's COALESCE() (where NULL = None)."""
    for val in values:
        if val is not None:
            return val
    return values[-1]


def admin_only(fn):
    """Mark an endpoint to be only accessible by admins. Must be above @page."""

    @functools.wraps(fn)
    async def wrapper(request, *args, **kwargs):
        if not context.user.is_admin:
            return HTTPResponse(
                body="403 Forbidden",
                status=403,
            )
        ret = fn(request, *args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        return ret

    return wrapper


def timed_cache(max_duration, *, key=None):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if key is not None:
                key_ = key(*args, **kwargs)
            else:
                key_ = None
            if not hasattr(fn, "_cached"):
                fn._cached = {}
                fn._cache_time = {}
            if (
                key_ not in fn._cached
                or monotonic() - fn._cache_time[key_] > max_duration.total_seconds()
            ):
                result = fn(*args, **kwargs)
                fn._cached[key_] = result
                fn._cache_time[key_] = monotonic()
            else:
                result = fn._cached[key_]
            return result
        return wrapper
    return decorator


def http_date(dt):
    # We're just assuming UTC here. That is a) probably correct in a production
    # setup, and b) it really doesn't matter; this is just to force caching to
    # work.
    if isinstance(dt, str):
        # 2025-05-04 09:39:50
        dt = datetime.fromisoformat(dt)
    return f"{dt:%a, %d %b %Y %H:%M:%S GMT}"


def cache_pls_headers(update_time=None):
    return {
        "Cache-Control": "max-age=86400",
        "Pragma": "public",
        "Last-Modified": http_date(update_time or startup_time),
        "Date": http_date(datetime.now()),
    }
