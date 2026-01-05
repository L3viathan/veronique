from sanic import Blueprint, file

static = Blueprint("static", url_prefix="/static")


@static.get("/htmx.js")
async def htmx_js(request):
    return await file("data/htmx.js", mime_type="text/javascript")


@static.get("/style.css")
async def style_css(request):
    return await file("data/style.css", mime_type="text/css")


@static.get("/mana-cost.css")
async def mana_cost_css(request):
    return await file("data/mana-cost.css", mime_type="text/css")


@static.get("/mana.svg")
async def mana_svg(request):
    return await file("data/mana.svg", mime_type="image/svg+xml")


@static.get("/prism.css")
async def prism_css(request):
    return await file("data/prism.css", mime_type="text/css")


@static.get("/pico.min.css")
async def pico_css(request):
    return await file("data/pico.min.css", mime_type="text/css")


@static.get("/prism.js")
async def prism_js(request):
    return await file("data/prism.js", mime_type="text/javascript")


@static.get("/sigma.min.js")
async def sigma_js(request):
    return await file("data/sigma.min.js", mime_type="text/javascript")


@static.get("/graphology.umd.min.js")
async def graphology_js(request):
    return await file("data/graphology.umd.min.js", mime_type="text/javascript")


@static.get("/graphology-library.min.js")
async def graphology_library_js(request):
    return await file("data/graphology-library.min.js", mime_type="text/javascript")


@static.get("/veronique.png")
async def veronique_png(request):
    return await file("data/veronique.png", mime_type="image/png")


@static.get("/leaflet.css")
async def leaflet_css(request):
    return await file("data/leaflet.css", mime_type="text/css")


@static.get("/leaflet.js")
async def leaflet_js(request):
    return await file("data/leaflet.js", mime_type="text/javascript")


@static.get("/images/marker-icon-2x.png")
async def marker_png(request):
    return await file("data/marker-icon-2x.png", mime_type="image/png")
