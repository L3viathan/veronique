from base64 import b64encode
from sanic import Blueprint, redirect

from veronique.settings import settings as S
from veronique.utils import admin_only, page, D, fragment
from veronique.context import context
from veronique.security import sign

settings = Blueprint("settings", url_prefix="/settings")


@settings.get("/")
@page
async def settings_form(request):
    d = "" if context.user.is_admin else " disabled"
    return "Settings", f"""
        <article>
            <header><h2>Settings</h2></header>
            <form method="POST">
                <h4>General</h4>
                <fieldset class="grid">
                    <label>
                    Application name
                    <input name="app_name" placeholder="Véronique"{d}>
                    <small>This will be shown as part of page titles.</small>
                    </label>
                    <label>
                    Page size
                    <input type="number" name="page_size" min=1 value="{S.page_size}">
                    <small>How many items to show in paginated pages.</small>
                    </label>
                </fieldset>
                <fieldset class="grid">
                    <label>
                    Default region
                    <input name="default_phone_region" placeholder="DE" pattern="[A-Z]{{2}}" maxlength="2" value="{S.default_phone_region or ""}"{d}>
                    <small>In phonenumber inputs, this will be assumed as the region, if none is specified via a + prefix.</small>
                    </label>
                </fieldset>
                <h4>Index page</h4>
                    <select name="index_type">
                        <option value="recent_events" {"selected" if S.index_type == "recent_events" else ""}>Recent events</option>
                        <option value="all_recent_events" {"selected" if S.index_type == "all_recent_events" else ""}>Recent events (including validity)</option>
                        <option value="newest_root_claims" {"selected" if S.index_type == "newest_root_claims" else ""}>Newest claims (roots only)</option>
                        <option value="newest_claims" {"selected" if S.index_type == "newest_claims" else ""}>Newest claims (all)</option>
                    </select>
                <fieldset class="grid">
                    <label>
                    Days back
                    <input type="number" name="index_days_back" min=1 value="{S.index_days_back}">
                    <small>How many days to look back for relevant events.</small>
                    </label>
                    <label>
                    Days ahead
                    <input type="number" name="index_days_ahead" min=1 value="{S.index_days_ahead}">
                    <small>How many days to look forwards for relevant events.</small>
                    </label>
                    <label>
                    Roundness
                    <input type="number" name="index_recent_events_mod" min=1 value="{S.index_recent_events_mod}">
                    <small>How significant anniversaries have to be (e.g. 5 for only anniversaries ending in 5 and 0)</small>
                    </label>
                </fieldset>
                <h4>Indexing</h4>
                <small>These weights influence the BM25 algorithm used for searching.</small>
                <fieldset class="grid">
                    <label>
                    k<sub>1</sub>
                    <input type="number" step="any" name="search_k_1" value="{S.search_k_1}"{d}>
                    </label>
                    <label>
                    b
                    <input type="number" step="any" name="search_b" value="{S.search_b}"{d}>
                    </label>
                    <label>
                    n
                    <input type="number" min=1 name="search_n" value="{S.search_n}"{d}>
                    <small>This is the <em>n</em> in n-gram. We use character n-grams.</small>
                    </label>
                </fieldset>
                {'''
                <fieldset>
                <a href="#" role="button" hx-swap="outerHTML" hx-post="/search/rebuild">Rebuild search index</a>
                <a href="#" role="button" hx-swap="outerHTML" hx-post="/settings/generate-token">Issue API token</a>
                </fieldset>
                ''' if context.user.is_admin else ""}

                <input type="submit" value="Save">
            </form>
        </article>
    """


@settings.post("/")
async def save_settings(request):
    form = D(request.form)
    S.page_size = form.get("page_size")
    S.default_phone_region = form.get("default_phone_region")
    S.index_days_ahead = form.get("index_days_ahead")
    S.index_days_back = form.get("index_days_back")
    S.index_type = form.get("index_type")
    S.index_recent_events_mod = form.get("index_recent_events_mod")
    if context.user.is_admin:
        S.app_name = form.get("app_name")
        S.search_k_1 = form.get("search_k_1")
        S.search_b = form.get("search_b")
        S.search_n = form.get("search_n")
    return redirect("/")


@settings.post("/generate-token")
@admin_only
@fragment
async def generate_token(request):
    token = b64encode(sign(context.user.payload).encode()).decode()
    return f"""
        <fieldset role="group">
        <input id="token" disabled value="{token}">
        <input type="hidden" name="password" value="{token}">
        <input type="button" value="copy" onclick="navigator.clipboard.writeText('{token}')">
        </fieldset>
    """
