import random
from collections import Counter, defaultdict
from itertools import cycle


def network_widget(claims, *, links_go_to="detail", force_labels=False, colormap=None, freeze_after=None):
    nodes_seen, edges_seen = set(), set()
    all_nodes, all_edges = [], []
    link_count = Counter()
    for c in claims:
        node, edges = c.graph_elements()
        if node["id"] not in nodes_seen:
            all_nodes.append(node)
            nodes_seen.add(node["id"])
        for edge in edges:
            k = frozenset([edge["source"], edge["target"]])
            if k not in edges_seen:
                all_edges.append(edge)
                edges_seen.add(k)
                link_count[edge["source"]] += 1
                link_count[edge["target"]] += 1
    all_edges = [
        edge
        for edge in all_edges
        if edge["source"] in nodes_seen
        and edge["target"] in nodes_seen
    ]

    parts = []
    if not freeze_after:
        parts.append("""
        <button id="playpause" onclick="handlePlayPause()" style="position: fixed; z-index: 2;">■</button>
        """)
    parts.append("""
    <div id="cy"></div>
    <script>
        var active = true;
        function handlePlayPause() {
          if (active) {
              fa2Layout.stop();
              document.getElementById("playpause").innerText = "▶\uFE0E";
          } else {
              fa2Layout.start();
              document.getElementById("playpause").innerText = "■";
          }
          active = !active;
        }
        var graph = new graphology.Graph();
        var fa2Layout = new graphologyLibrary.FA2Layout(graph);
        var draggedNode = null;
    """)
    if freeze_after:
        parts.append(f"window.setTimeout(() => {{fa2Layout.stop();}}, {freeze_after * 1000});")

    maybe_force_labels = (
        ", forceLabel: true"
        if len(all_nodes) < 100 or force_labels
        else ""
    )
    colors = defaultdict(cycle(["red", "green", "blue", "orange", "purple"]).__next__)
    for node in all_nodes:
        parts.append(f'graph.addNode("{node["id"]}", {{label: "{node["label"]}", x: {random.random()}, y: {random.random()}, size: {1 if len(all_nodes) > 30 else 10}, color: "{colors[node["cat"] if not colormap else colormap[node["id"]]]}"{maybe_force_labels}}});\n')

    for edge in all_edges:
        parts.append(f'graph.addEdge("{edge["source"]}", "{edge["target"]}", {{label: "{edge["label"]}", size: {1 if len(all_edges) > 30 else 5}, color: "grey", type: "{edge["type"]}"}});\n')

    parts.append(f"""
        var sig = new Sigma(graph, document.getElementById("cy"), {{renderEdgeLabels: true, allowInvalidContainer: true}});
        sig.on("downNode", (e) => {{
          draggedNode = e.node;
        }});
        sig.on("moveBody", (e) => {{
          draggedNode = null;
        }});
        sig.on("upNode", (e) => {{
          if (draggedNode) {{
            location.href = "/claims/" + draggedNode{' + "/network"' if links_go_to == "network" else ''};
          }}
        }});

        fa2Layout.start();
    </script>
    """)
    return "".join(parts)
