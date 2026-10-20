from base64 import b64encode

from sanic import Blueprint, redirect

from veronique.context import context
from veronique.html import H
from veronique.security import sign
from veronique.settings import settings as S
from veronique.utils import D, admin_only, fragment, page

settings = Blueprint("settings", url_prefix="/settings")


@settings.get("/")
@page
async def settings_form(request):
    d = "" if context.user.is_admin else " disabled"
    return "Settings", H.article(
        H.header(H.h2("Settings")),
        H.form(
            H.h4("General"),
            H.fieldset(
                H.label(
                    "Application name",
                    H.input(name="app_name", placeholder="Véronique"),
                ),
                H.label(
                    "Page size",
                    H.input(type="number", name="page_size", min="1", value=str(S.page_size)),
                    H.small("How many items to show in paginated pages."),
                ),
                cls="grid",
            ),
            H.fieldset(
                H.label(
                    "Default region",
                    H.input(
                        name="default_phone_region",
                        placeholder="DE",
                        pattern="[A-Z]{2}",
                        maxlength="2",
                        value=str(S.default_phone_region or ""),
                        disabled=not context.user.is_admin,
                    ),
                    H.small("In phonenumber inputs, this will be assumed as the region, if none is specified via a + prefix."),
                ),
                cls="grid",
            ),
            H.h4("Index page"),
            H.select(
                H.option(
                    "Recent events",
                    value="recent_events",
                    selected=S.index_type=="recent_events",
                ),
                H.option(
                    "Recent events (including validity)",
                    value="all_recent_events",
                    selected=S.index_type=="all_recent_events",
                ),
                H.option(
                    "Newest entities",
                    value="newest_entities",
                    selected=S.index_type=="newest_entities",
                ),
                H.option(
                    "Newest claims",
                    value="newst_claims",
                    selected=S.index_type=="newst_claims",
                ),
                name="index_type",
            ),
            H.fieldset(
                H.label(
                    "Days back",
                    H.input(type="number", name="index_days_back", min="1", value=str(S.index_days_back)),
                    H.small("How many days to look back for relevant events."),
                ),
                H.label(
                    "Days ahead",
                    H.input(type="number", name="index_days_ahead", min="1", value=str(S.index_days_ahead)),
                    H.small("How many days to look forwards for relevant events."),
                ),
                H.label(
                    "Roundness",
                    H.input(type="text", name="index_recent_events_mod", value=str(S.index_recent_events_mod)),
                    H.small("How significant anniversaries have to be (e.g. 5 for only anniversaries ending in 5 and 0)"),
                ),
                cls="grid",
            ),
            H.h4("Indexing"),
            H.small("These weights influence the BM25 algorithm used for searching."),
            H.fieldset(
                H.label(
                    "k",
                    H.sub("1"),
                    H.input(type="number", step="any", name="search_k_1", value=str(S.search_k_1), disabled=not context.user.is_admin),
                ),
                H.label(
                    "b",
                    H.input(type="number", step="any", name="search_b", value=str(S.search_b), disabled=not context.user.is_admin),
                ),
                H.label(
                    "n",
                    H.input(type="number", step="any", name="search_n", value=str(S.search_n), disabled=not context.user.is_admin),
                    H.small("This is the ", H.em("n"), " in n-gram. We use character n-grams."),
                ),
                cls="grid",
            ),
            H.h4("Maps"),
            H.fieldset(
                H.label(
                    "Tile provider URL",
                    H.input(type="text", name="map_tile_url", value=str(S.map_tile_url)),
                    H.small("Needs to contain ", H.tt("{x}"), ", ", H.tt("{y}"), " and ", H.tt("{z}"), "."),
                ),
                H.label(
                    "Location link format",
                    H.input(type="text", name="location_link_template", value=str(S.location_link_template)),
                    H.small("Needs to contain ", H.tt("{}"), "."),
                ),
                cls="grid",
            ),
            H.fieldset(
                H.label(
                    "Tile provider name",
                    H.input(type="text", name="map_tile_attribution_label", value=str(S.map_tile_attribution_label)),
                ),
                H.label(
                    "Tile provider attribution URL",
                    H.input(type="text", name="map_tile_attribution_link", value=str(S.map_tile_attribution_link)),
                ),
                cls="grid",
            ),
            H.h4("Sources"),
            H.label(
                "Default source type",
                H.select(
                    H.option("Text", value="T", selected=S.default_source_type=="T"),
                    H.option("Website", value="U", selected=S.default_source_type=="U"),
                    H.option("Entity", value="E", selected=S.default_source_type=="E"),
                ),
            ),
            H.fieldset(
                H.a("Rebuild search index", href="#", role="button", hx_swap="outerMorph", hx_post="/search/rebuild"),
                H.a("Issue API token", href="#", role="button", hx_swap="outerMorph", hx_post="/settings/generate-token"),
            ) if context.user.is_admin else None,
            H.input(type="submit", value="Save"),
            method="POST",
        ),
    )


@settings.post("/")
async def save_settings(request):
    form = D(request.form)
    S.page_size = form.get("page_size")
    S.default_phone_region = form.get("default_phone_region")
    S.index_days_ahead = form.get("index_days_ahead")
    S.index_days_back = form.get("index_days_back")
    S.index_type = form.get("index_type")
    S.index_recent_events_mod = form.get("index_recent_events_mod")
    S.default_source_type = form.get("default_source_type")
    if context.user.is_admin:
        S.app_name = form.get("app_name")
        S.search_k_1 = form.get("search_k_1")
        S.search_b = form.get("search_b")
        S.search_n = form.get("search_n")
        S.map_tile_attribution_link = form.get("map_tile_attribution_link")
        S.map_tile_attribution_label = form.get("map_tile_attribution_label")
        S.map_tile_url = form.get("map_tile_url")
        S.location_link_template = form.get("location_link_template")
    return redirect("/")


@settings.post("/generate-token")
@admin_only
@fragment
async def generate_token(request):
    token = b64encode(sign(context.user.payload).encode()).decode()
    return H.fieldset(
        H.input(id="token", disabled=True, value=token),
        H.input(type="hidden", name="password", value=token),
        H.input(type="button", value="copy", onclick=f"navigator.clipboard.writeText('{token}')"),
        role="group",
    )
