from itertools import chain
from sanic import Sanic, html, file
import controller as ctrl

app = Sanic("Veronique")


DISPLAYERS = {
    "string": lambda val: f'"{val}"',
}

@app.route("/")
async def index(request):
    return html(
        """
        <!DOCTYPE html>
        <html>
            <head>
                <script src="htmx.js"></script>
                <title>Veronique</title>
            </head>
            <body>
                <nav>
                    <a hx-get="/creatures" hx-target="#container">Creatures</a>
                    <a hx-get="/properties" hx-target="#container">Properties</a>
                </nav>
                <hr>
                <div id="container"></div>
            </body>
        </html>
        """
    )


@app.route("/creatures")
async def list_creatures(request):
    page = request.args.get("page", 1)
    return html(
        "<br>".join(
            f'<a hx-get="/creatures/{id}" hx-target="#container">{name}</a>'
            for id, name in ctrl.list_creatures(page=page)
        )
    )


@app.route("/creatures/<creature_id>")
async def view_creatures(request, creature_id):
    facts = ctrl.get_creature(creature_id)
    if "name" in facts and facts["name"]:
        name = facts["name"][0]["value"]
    else:
        name = "(no name)"
    display_facts = []
    for row in chain.from_iterable(facts.values()):
        if row["other_creature_id"]:
            display_facts.append(f'<li>{row["label"]}: <a hx-target="#container" hx-get="/creatures/{row["other_creature_id"]}">TBD other creature</a></li>')
        else:
            display_facts.append(f"<li>{row['label']}: {DISPLAYERS[row['type']](row['value'])}</li>")
    return html(
        f"""
        <h2>{name}</h2>
        <ul>
            {"".join(display_facts)}
        </ul>
        """
    )


@app.route("/properties")
async def list_properties(request):
    return html(
        """
        properties
        """
    )


@app.route("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")
