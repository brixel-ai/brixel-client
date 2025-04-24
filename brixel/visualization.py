# brixel/visualization.py
from __future__ import annotations
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

def display_plan(plan: dict[str, Any], *, filename: str | None = None) -> None:
    """
    Pretty-print a Brixel plan as a vertical flow-chart.

    • Sub-plans are rendered as side-by-side clusters (L→R)
    • Nodes inside a sub-plan are stacked top-to-bottom in the order of `index`
    • If a node has `has_children`, its children are indented inside a mini-cluster
    • Edges follow the numerical order: 3 → 4 → 5 …

    Optional extras (`pip install brixel[viz]`) are required.
    """
    try:
        import pydot
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
    except ImportError:
        raise ImportError(
            "Graph visualisation needs the optional extras:\n"
            "  pip install brixel[viz]   # includes graphviz, pydot, matplotlib"
        )

    # ────────────────────────────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────────────────────────────
    def add_node(g: pydot.Graph, nid: str, node: dict, colour: str):
        """
        Adds a node with a rich label including inputs (excluding children).
        """
        label = f"[{node['index']}] ({node['name']}) {node.get('title')}"
        inputs = node.get("inputs", {})
        output = node.get("output")
        
        # Ignore 'children' key if it's a block node
        if node.get("has_children"):
            inputs = {k: v for k, v in inputs.items() if k != "children"}

        # Format inputs nicely
        if inputs:
            formatted_inputs = "\n".join(f"{k} = {v}" for k, v in inputs.items())
            label += f"\n---\ninputs:\n{formatted_inputs}"
        if output:
            label += f"\n---\noutput = {output}"

        g.add_node(pydot.Node(
            nid,
            label=label,
            shape="box",
            style="filled,rounded",
            fillcolor=colour,
            fontsize="9"
        ))

        
    # ───────────── recursively add children ──────────────
    def add_children(parent_id: str, child_nodes: list[dict], parent_cluster: pydot.Cluster):
        """
        Add children (and grand-children …) recursively.
        """
        if not child_nodes:
            return

        # create a dotted sub-cluster for this generation
        child_cluster = pydot.Cluster(
            f"{parent_id}_children",
            label="",
            style="dotted",
            color=colour,
            rankdir="TB",
        )

        prev_cid = None
        for child in sorted(child_nodes, key=lambda c: c["index"]):
            cid = f"{sid}_{child['index']}"
            clabel = f"{child['index']}. {child.get('title') or child['name']}"
            add_node(child_cluster, cid, child, colour)

            # vertical order between siblings
            if prev_cid:
                dot.add_edge(pydot.Edge(prev_cid, cid))
            prev_cid = cid

            # edge parent → first child
            if child == child_nodes[0]:
                dot.add_edge(pydot.Edge(parent_id, cid))

            # recursion for grand-children
            if child.get("has_children"):
                gkids = child.get("inputs", {}).get("children", [])
                add_children(cid, gkids, child_cluster)

        parent_cluster.add_subgraph(child_cluster)


    colours = {
        "local": "#B5D9FF",
        "hosted": "#B9F6C5",
        "external": "#FFE1AF"
    }

    dot = pydot.Dot("brixel_plan", graph_type="digraph", rankdir="TB", splines="ortho")

    for sub in plan.get("sub_plans", []):
        sid = sub["id"]
        agent_id = sub["agent"]["id"]
        a_type = sub["agent"]["type"]
        colour = colours.get(a_type, "#E0E0E0")

        cluster = pydot.Cluster(
            f"cluster_{sid}",
            label=f"Sub-plan #{sid}  |  agent: {agent_id} ({a_type})",
            style="dashed",
            color=colour.replace("FF", "80"),
            rankdir="TB"
        )

        index_to_node = {}
        for node in sorted(sub["plan"], key=lambda n: n["index"]):
            idx = node["index"]
            nid = f"{sid}_{idx}"
            add_node(cluster, nid, node, colour)
            index_to_node[idx] = nid

        # Edges by index order
        indices = sorted(index_to_node)
        for i in range(len(indices) - 1):
            dot.add_edge(pydot.Edge(index_to_node[indices[i]], index_to_node[indices[i + 1]]))

        # Handle children
        
        for node in sub["plan"]:
            if node.get("has_children"):
                add_children(
                    parent_id=index_to_node[node["index"]],
                    child_nodes=node.get("inputs", {}).get("children", []),
                    parent_cluster=cluster
                )
        dot.add_subgraph(cluster)

    # --- Render ---
    out_png: Path
    if filename:
        out_png = Path(filename).with_suffix(".png")
    else:
        out_png = Path(NamedTemporaryFile(suffix=".png", delete=False).name)

    dot.write_png(out_png)

    if not filename:
        img = mpimg.imread(out_png)
        plt.figure(figsize=(14, 6))
        plt.imshow(img)
        plt.axis("off")
        plt.title("Brixel execution plan", fontsize=14)
        plt.tight_layout()
        plt.show()
        out_png.unlink(missing_ok=True)
    else:
        print(f"Graph saved to {out_png.resolve()}")
