"""Shared Graphviz style constants for diagrams."""

GRAPH_ATTR = {
    "fontsize": "14",
    "bgcolor": "white",
    "pad": "0.5",
    "rankdir": "TB",
    "splines": "ortho",
}

EDGE_COLORS = {
    "subnet": "gray",
    "route": "blue",
    "igw": "green",
    "nat": "purple",
    "lambda": "orange",
    "peering": "red",
    "tgw": "brown",
    "lb": "teal",
}
