"""
Topology loader — reads data/topology.json and provides graph traversal utilities.
PRD §14: static topology for MVP; no auto-discovery.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


TOPOLOGY_PATH = Path(__file__).parent.parent.parent / "data" / "topology.json"
TOPOLOGY_URL = "https://logs.nonprod.nexus.ensylon.com/sim/reference/service-dependency-graph"


@lru_cache(maxsize=1)
def load_topology() -> dict[str, list[str]]:
    """
    Load service dependency graph.
    Attempts to fetch from simulator reference endpoint (PS §6.1).
    Falls back to data/topology.json if network or endpoint fails.
    """
    try:
        resp = httpx.get(TOPOLOGY_URL, timeout=4.0)
        resp.raise_for_status()
        data = resp.json()
        logger.info("Loaded service dependency graph from %s", TOPOLOGY_URL)
        return data
    except Exception as e:
        logger.warning(
            "Could not fetch topology from %s (%s). Falling back to %s",
            TOPOLOGY_URL,
            e,
            TOPOLOGY_PATH,
        )
        if not TOPOLOGY_PATH.exists():
            raise FileNotFoundError(f"Topology fallback not found at {TOPOLOGY_PATH}") from e
        with open(TOPOLOGY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def get_hop_distance(service_a: str, service_b: str, max_hops: int = 4) -> int:
    """
    BFS hop distance between two services in the topology graph.
    Returns max_hops+1 if unreachable (= no topology relationship).
    Treats the graph as undirected for correlation purposes.
    """
    if service_a == service_b:
        return 0

    topo = load_topology()

    # Build undirected adjacency
    adj: dict[str, set[str]] = {}
    for src, dsts in topo.items():
        adj.setdefault(src, set()).update(dsts)
        for dst in dsts:
            adj.setdefault(dst, set()).add(src)

    visited = {service_a}
    queue = [(service_a, 0)]
    while queue:
        node, hops = queue.pop(0)
        if hops >= max_hops:
            continue
        for neighbor in adj.get(node, set()):
            if neighbor == service_b:
                return hops + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, hops + 1))

    return max_hops + 1


def are_topology_related(service_a: str, service_b: str, max_hops: int = 3) -> bool:
    """Returns True if the two services are within max_hops of each other."""
    return get_hop_distance(service_a, service_b) <= max_hops
