from sanic import Blueprint, redirect

from veronique.settings import settings as S
from veronique.utils import admin_only, page, D

settings = Blueprint("settings", url_prefix="/settings")


@settings.get("/")
@admin_only
@page
async def settings_form(request):
    return "Settings", f"""
        <article>
            <header><h2>Settings</h2></header>
            <form method="POST">
                <h4>General</h4>
                <fieldset class="grid">
                    <label>
                    Application name
                    <input name="page_size" placeholder="Véronique">
                    <small>This will be shown as part of page titles.</small>
                    </label>
                    <label>
                    Page size
                    <input type="number" name="page_size" min=1 value="{S.page_size}">
                    <small>How many items to show in paginated pages.</small>
                    </label>
                </fieldset>
                <h4>Index page</h4>
                    <select name="index_type">
                        <option value="recent_events" {"selected" if S.index_type == "recent_events" else ""}>Recent events</option>
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
                </fieldset>
                <h4>Maintenance</h4>
                <fieldset>
                <a href="#" role="button" hx-swap="outerHTML" hx-post="/search/rebuild">Rebuild search index</a>
                </fieldset>

                <input type="submit" value="Save">
            </form>
        </article>
    """


@settings.post("/")
@admin_only
async def save_settings(request):
    form = D(request.form)
    S.app_name = form.get("app_name")
    S.page_size = form.get("page_size")
    S.index_days_ahead = form.get("index_days_ahead")
    S.index_days_back = form.get("index_days_back")
    S.index_type = form.get("index_type")
    return redirect("/")
