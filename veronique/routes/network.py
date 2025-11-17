import json

from sanic import Blueprint

import veronique.objects as O
from veronique.utils import page
from veronique.db import IS_A, ROOT

network = Blueprint("network", url_prefix="/network")


@network.get("/")
@page
async def show_network(request):
    all_categories = list(O.Claim.all_categories(page_size=9999))
    if "categories" in request.args:
        ids = [int(part.removeprefix("cat")) for part in request.args["categories"]]
        categories = {O.Claim(category_id) for category_id in ids}
    else:
        categories = None
    all_verbs = list(O.Verb.all(data_type="%directed_link"))
    if "verbs" in request.args:
        ids = [int(part.removeprefix("verb")) for part in request.args["verbs"]]
        verbs = [O.Verb(verb_id) for verb_id in ids]
    else:
        verbs = all_verbs
    claims = (
        c
        for c in O.Claim.all_labelled(page_size=9999)
        if categories is None
        or ({cat.object for cat in c.get_data().get(IS_A, set())} & categories)
    )
    node_ids = set()
    elements, all_edges = [], []
    for c in claims:
        node, edges = c.graph_elements(verbs=verbs)
        elements.append(node)
        node_ids.add(node["data"]["id"])
        all_edges.extend(edges)
    for edge in all_edges:
        if edge["data"]["source"] in node_ids and edge["data"]["target"] in node_ids:
            elements.append(edge)

    return "Network", f"""
    <form id="networkform">
    <fieldset class="grid">
    <details class="dropdown">
      <summary>Select Categories...</summary>
      <ul>
      {
            "".join(
                f'''<li><input
                  type="checkbox"
                  id="cat{cat.id}"
                  name="categories"
                  value="cat{cat.id}"
                  {"checked" if categories is None or cat in categories else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="cat{cat.id}">{cat:label}</label></li>
              '''
                for cat in all_categories
            )
        }
      </ul>
    </details>
    <details class="dropdown">
    <summary>Select Verbs...</summary>
      <ul>
      {
            "".join(
                f'''<li><input
                  type="checkbox"
                  id="verb{verb.id}"
                  name="verbs"
                  value="verb{verb.id}"
                  {"checked" if verb in verbs else ""}
                  hx-get="/network"
                  hx-include="#networkform"
                  hx-swap="outerHTML"
                  hx-target="#container"
                  hx-select="#container"
              />
              <label for="verb{verb.id}">{verb.label}</label></li>
              '''
                for verb in all_verbs
                if verb.id not in (IS_A, ROOT)
            )
        }
      </ul>
    </details>
    </fieldset>
    </form>
    <div id="cy"></div>
    <script>
        var cy = cytoscape({{
            container: document.getElementById("cy"),
            elements: [
            {",".join(json.dumps(element) for element in elements)}
            ],
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'label': 'data(label)',
                        'width': '5px',
                        'height': '5px',
                        'font-size': '5pt',
                    }}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'label': 'data(label)',
                        'font-size': '4pt',
                        'width': '1px',
                        'line-opacity': 0.2,
                    }}
                }},
            ],
        }});
        layout = cy.layout({{
            name: 'cose',
            initialTemp: 4000,
        }});
        layout.run();
    </script>
    """
