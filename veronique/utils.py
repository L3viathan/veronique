import functools
from types import CoroutineType

from sanic import html, HTTPResponse

from veronique.db import ROOT
from veronique.settings import settings as S
from veronique.context import context


with open("data/template.html") as f:
    TEMPLATE = f.read().format

def _error(msg):
    return f"""
    <aside id="errors"><strong>Error:</strong> {msg} <span class="dismiss" hx-get="about:blank" hx-on:click="document.getElementById('errors').remove()">×</span></aside>
    """


def _notice(msg):
    return f"""
    <aside id="notices"><strong>Info:</strong> {msg} <span class="dismiss" hx-get="about:blank" hx-on:click="document.getElementById('notices').remove()">×</span></aside>
    """


def D(multival_dict):
    return {key: val[0] for key, val in multival_dict.items()}


def pagination(url, page_no, *, more_results=True, allow_negative=False):
    if page_no == 1 and not more_results:
        return ""
    q = "&" if "?" in url else "?"
    return f"""<br>
        <a
            role="button"
            class="prev"
            href="{url}{q}page={page_no - 1}"
            {"disabled" if page_no == 1 and not allow_negative else ""}
        >&lt;</a>
        <a
            class="next"
            role="button"
            href="{url}{q}page={page_no + 1}"
            {"disabled" if not more_results else ""}
        >&gt;</a>
    """


def fragment(fn):
    """Mark an endpoint as returning HTML, but not a full page."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ret = fn(*args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, HTTPResponse):
            return ret
        return html(ret)

    return wrapper


def page(fn):
    """Mark an endpoint as returning a full standalone page."""

    @functools.wraps(fn)
    async def wrapper(request, *args, **kwargs):
        ret = fn(request, *args, **kwargs)
        if isinstance(ret, CoroutineType):
            ret = await ret
        if isinstance(ret, str):
            title = S.app_name
        elif isinstance(ret, HTTPResponse):
            return ret
        else:
            title, ret = ret
            title = f"{title} — {S.app_name}"

        gotos = []
        for page_name, restricted in [
            ("claims", False),
            ("verbs", False),
            ("network", False),
            ("queries", False),
            ("users", True),
        ]:
            if restricted and not context.user.is_admin:
                gotos.append(f'<li><a href="#" disabled>{page_name.title()}</a></li>')
            else:
                gotos.append(f'<li><a href="/{page_name}">{page_name.title()}</a></li>')
        if context.user.is_admin:
            news = """
            <li>
                <details class="dropdown clean">
                    <summary id="add-button">+
                    </summary>
                    <ul>
                        <li><a href="/claims/new-root">Root claim</a></li>
                        <li><a href="/verbs/new">Verb</a></li>
                        <li><a href="/queries/new">Query</a></li>
                        <li><a href="/users/new">User</a></li>
                    </ul>
                </details>
            </li>
            """
        elif context.user.can("write", "verb", ROOT):
            news = """
            <li>
                <a href="/claims/new-root" id="add-button">+</a>
            </li>
            """
        else:
            news = ""
        user = f"""
        <li>
            <details class="dropdown">
                <summary>{context.user.name}</summary>
                <ul dir="rtl">
                    {'<li><a href="/settings">Settings</a></li>' if context.user.is_admin else ""}
                    <li><a href="/logout">Logout</a></li>
                </ul>
            </details>
        </li>
        """
        return html(
            TEMPLATE(
                title=title,
                content=ret,
                gotos="".join(gotos),
                news=news,
                user=user,
                errors=_error(request.args["err"][0]) if "err" in request.args else "",
            )
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
