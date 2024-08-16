from itertools import chain
from sanic import Sanic, html, file
import controller as ctrl
from property_types import TYPES

app = Sanic("Veronique")


def D(multival_dict):
    return {key: val[0] for key, val in multival_dict.items()}

def _display_created(timestamp=None):
    if timestamp:
        return f'<span style="font-size: xx-small;">created {timestamp}</span>'
    return '<span style="font-size: xx-small;">created just now</span>'


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
                    <a hx-get="/types" hx-target="#container">Types</a>
                </nav>
                <hr>
                <div id="container"></div>
            </body>
        </html>
        """
    )


@app.get("/types")
async def list_types(request):
    return html("<br>".join(TYPES))


@app.get("/creatures")
async def list_creatures(request):
    page = request.args.get("page", 1)
    return html(
        "<br>".join(
            f'<a hx-get="/creatures/{id}" hx-target="#container">{name}</a>'
            for id, name in ctrl.list_creatures(page=page)
        )
        + """
        <br>
        <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
        """
    )


@app.get("/creatures/new")
async def new_creature_form(request):
    return html(
        """
        <form hx-post="/creatures/new" hx-swap="outerHTML">
            <input name="name" placeholder="name"></input>
            <button type="submit">»</button>
        </form>
    """
    )


@app.post("/creatures/new")
async def new_creature(request):
    name = D(request.form)["name"]
    creature_id = ctrl.add_creature(name)
    return html(
        f"""
        <a hx-get="/creatures/{creature_id}" hx-target="#container">{name}</a>
        <br>
        <button hx-get="/creatures/new" hx-swap="outerHTML">New creature</button>
    """
    )


@app.get("/creatures/<creature_id>")
async def view_creature(request, creature_id: int):
    facts = ctrl.get_creature_facts(creature_id)
    name = ctrl.get_creature_name(creature_id)
    display_facts = []
    for row in chain.from_iterable(facts.values()):
        display_facts.append(
            f"<li>{row['label']}: {TYPES[row['type']].display_html(row['value'])}{_display_created(row['created_at'])}</li>"
        )
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
            <select name="property" hx-get="/facts/new/{creature_id}/property" hx-target="#valueinput" hx-swap="innerHTML">
                <option selected disabled>--Property--</option>
                {"".join(f'''<option value="{id}">{label} <em>({type})</em></option>''' for id, label, type in props)}
            </select>
            <span id="valueinput"></span>
        </form>
        """
    )


@app.get("/facts/new/<creature_id>/property")
async def new_fact_form_property_input(request, creature_id: int):
    label, type = ctrl.get_property(int(D(request.args)["property"]))
    return html(
        f"""
        {TYPES[type].input_html(creature_id)}
        <button type="submit">»</button>
        """
    )


@app.post("/facts/new/<creature_id>")
async def new_fact(request, creature_id: int):
    form = D(request.form)
    property_id = int(form["property"])
    label, type = ctrl.get_property(property_id)
    value = form["value"]
    ctrl.add_fact(creature_id, property_id, value)
    # FIXME: replace value with value from DB
    return html(
        f"""
        <li>{label}: {TYPES[type].display_html(value)}{_display_created()}</li>
        <button hx-get="/facts/new/{creature_id}" hx-swap="outerHTML">New fact</button>
        """
    )


@app.get("/properties")
async def list_properties(request):
    return html(
        "<br>".join(
            f"{label} <em>({type})</em>" for id, label, type in ctrl.list_properties()
        )
        + """
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
        """
    )


@app.get("/properties/new")
async def new_property_form(request):
    return html(
        f"""
        <form hx-post="/properties/new" hx-swap="outerHTML">
            <input name="label" placeholder="label"></input>
            <select name="type" hx-get="/properties/new/step2" hx-target="#step2" hx-swap="innerHTML">
            <option selected disabled>--Type--</option>
            {"".join(f'''<option value="{type}">{type}</option>''' for type in TYPES)}
            </select>
            <span id="step2"></span>
        </form>
    """
    )


@app.get("/properties/new/step2")
async def new_property_form_step2(request):
    type = D(request.args)["type"]
    if type != "creature":
        return html('<button type="submit">»</button>')
    return html(
        """
        <select name="reflectivity" hx-get="/properties/new/step3" hx-target="#step3" hx-swap="innerHTML">
            <option selected disabled>--Reflectivity--</option>
            <option value="none">unidirectional</option>
            <option value="self">self-reflected</option>
            <option value="other">reflected</option>
        </select>
        <span id="step3"></span>
    """
    )


@app.get("/properties/new/step3")
async def new_property_form_step3(request):
    reflectivity = D(request.args)["reflectivity"]
    if reflectivity in ("none", "self"):
        return html('<button type="submit">»</button>')
    return html(
        """
        <input name="inversion"></input>
        <button type="submit">»</button>
    """
    )


@app.post("/properties/new")
async def new_property(request):
    form = D(request.form)
    ctrl.add_property(
        form["label"],
        form["type"],
        reflected_property_name=(
            None
            if form.get("reflectivity", "none") == "none"
            else ctrl.SELF
            if form["reflectivity"] == "self"
            else form["inversion"]
        ),
    )
    return html(f"""
        {form['label']} <em>({form['type']})</em>
        <br>
        <button hx-get="/properties/new" hx-swap="outerHTML">New property</button>
    """)


@app.get("/htmx.js")
async def htmx_js(request):
    return await file("htmx.js", mime_type="text/javascript")
