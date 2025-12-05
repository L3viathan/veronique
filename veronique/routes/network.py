import random
from collections import defaultdict
from itertools import cycle

from sanic import Blueprint, HTTPResponse

import veronique.objects as O
from veronique.context import context
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
    if "query" in request.args:
        query_id = int(request.args.get("query"))
        if not context.user.can("view", "query", query_id):
            return HTTPResponse(
                body="403 Forbidden",
                status=403,
            )
        query = O.Query(query_id)
        result = query.run(
            page_no=0,
            page_size=9999,
        )
        claims = (
            O.Claim(row[request.args.get("col" if "col" in request.args else "node_c")])
            for row in result
        )
    else:
        claims = (
            c
            for c in O.Claim.all_labelled(page_size=9999)
            if categories is None
            or ({cat.object for cat in c.get_data().get(IS_A, set())} & categories)
        )
    nodes_seen, edges_seen = set(), set()
    all_nodes, all_edges = [], []
    for c in claims:
        node, edges = c.graph_elements(verbs=verbs)
        if node["id"] not in nodes_seen:
            all_nodes.append(node)
            nodes_seen.add(node["id"])
        for edge in edges:
            k = frozenset([edge["source"], edge["target"]])
            if k not in edges_seen:
                all_edges.append(edge)
                edges_seen.add(k)
    all_edges = [
        edge
        for edge in all_edges
        if edge["source"] in nodes_seen
        and edge["target"] in nodes_seen
    ]

    parts = [f"""<form id="networkform">
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
                  hx-push-url="true"
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
                  hx-push-url="true"
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
    <button id="playpause" onclick="handlePlayPause()" style="position: fixed; z-index: 2;">■</button>
    <div id="cy"></div>
    <script>
        var active = true;
        function handlePlayPause() {{
          if (active) {{
              fa2Layout.stop();
              document.getElementById("playpause").innerText = "▶\uFE0E";
          }} else {{
              fa2Layout.start();
              document.getElementById("playpause").innerText = "■";
          }}
          active = !active;
        }}
        var graph = new graphology.Graph();
        var fa2Layout = new graphologyLibrary.FA2Layout(graph);
        var draggedNode = null;
    """]

    colors = defaultdict(cycle(["red", "green", "blue", "orange", "purple"]).__next__)
    for node in all_nodes:
        parts.append(f'graph.addNode("{node["id"]}", {{label: "{node["label"]}", x: {random.random()}, y: {random.random()}, size: 3, color: "{colors[node["cat"]]}"}});\n')

    for edge in all_edges:
        parts.append(f'graph.addEdge("{edge["source"]}", "{edge["target"]}", {{label: "{edge["label"]}", size: 1, color: "grey", type: "{edge["type"]}"}});\n')

    parts.append("""
        var sig = new Sigma(graph, document.getElementById("cy"), {renderEdgeLabels: true, allowInvalidContainer: true});
        sig.on("downNode", (e) => {
          draggedNode = e.node;
        });
        sig.on("moveBody", (e) => {
          draggedNode = null;
        });
        sig.on("upNode", (e) => {
          if (draggedNode) {
            location.href = "/claims/" + draggedNode;
          }
        });

        fa2Layout.start();
        window.setTimeout(function(){{fa2Layout.stop();}}, 5000);
    </script>
    """)
    return "Network", "".join(parts)
