from itertools import chain
from sanic import Sanic, html, file
import controller as ctrl
from property_types import TYPES

app = Sanic("Veronique")



@app.get("/")
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


@app.get("/creatures")
async def list_creatures(request):
    page = request.args.get("page", 1)
    return html(
        "<br>".join(
            f'<a hx-get="/creatures/{id}" hx-target="#container">{name}</a>'
            for id, name in ctrl.list_creatures(page=page)
        ) + """
        <br>
        <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
        """
    )


@app.get("/creatures/new")
async def new_creature_form(request):
    return html("""
        <form hx-post="/creatures/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <button type="submit">»</button>
        </form>
    """)


@app.post("/creatures/new")
async def new_creature(request):
    name = request.form["name"][0]
    creature = ctrl.add_creature()
    prop = next(id for id, label, type in ctrl.list_properties() if label == "name")
    creature_id = ctrl.add_fact(creature, prop, name)
    return html(f"""
        <a hx-get="/creatures/{creature_id}" hx-target="#container">{name}</a>
        <br>
        <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
    """)


@app.get("/creatures/<creature_id>")
async def view_creature(request, creature_id: int):
    facts = ctrl.get_creature(creature_id)
    if "name" in facts and facts["name"]:
        name = facts["name"][0]["value"]
    else:
        name = "(no name)"
    display_facts = []
    for row in chain.from_iterable(facts.values()):
        display_facts.append(f"<li>{row['label']}: {TYPES[row['type']].display_html(row['value'])}</li>")
    return html(
        f"""
        <h2>{name}</h2>
        <ul>
            {"".join(display_facts)}
            <button hx-get="/facts/new/{creature_id}" hx-swap="outerHTML">New fact</button>
        </ul>
        """
    )


@app.get("/facts/new/<creature_id>")
async def new_fact_form(request, creature_id: int):
    props = ctrl.list_properties()
    return html(
        f"""
        <form hx-post="/facts/new/{creature_id}" hx-swap="outerHTML">
            <select name="property" hx-get="/facts/new/{creature_id}/property" hx-target="#valueinput">
                <option value="">--Property--</option>
                {"".join(f'''<option value="{id}">{label} <em>({type})</em></option>''' for id, label, type in props)}
            </select>
            <div id="valueinput"></div>
        </form>
        """
    )


@app.get("/facts/new/<creature_id>/property")
async def new_fact_form_property_input(request, creature_id: int):
    label, type = ctrl.get_property(int(request.args["property"][0]))
    return html(
        f"""
        {TYPES[type].input_html(creature_id)}
        <button type="submit">»</button>
        """
    )


@app.post("/facts/new/<creature_id>")
async def new_fact(request, creature_id: int):
    property_id = int(request.form["property"][0])
    label, type = ctrl.get_property(property_id)
    value = request.form["value"][0]
    ctrl.add_fact(creature_id, property_id, value)
    # FIXME: replace value with value from DB
    return html(
        f"""
        <li>{label}: {TYPES[type].display_html(value)}</li>
        <button hx-get="/facts/new/{creature_id}" hx-swap="outerHTML">New fact</button>
        """
    )


@app.get("/properties")
async def list_properties(request):
    return html(
        "<br>".join(
            f"{label} <em>({type})</em>"
            for id, label, type in ctrl.list_properties()
        )
    )


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")
