import heapq

from graphlib import CycleError, TopologicalSorter

from .analyzer import ModuleInfo


def build_dependency_graph(
    analyses: dict[str, ModuleInfo],
) -> dict[str, set[str]]:
    """Build an adjacency list mapping each module to the set it depends on.

    Only includes edges to modules that actually exist in *analyses*.
    """
    graph: dict[str, set[str]] = {}
    for mod_name, info in analyses.items():
        deps: set[str] = set()
        for imp in info.local_imports:
            if imp in analyses:
                deps.add(imp)
        graph[mod_name] = deps
    return graph


def topological_sort(
    graph: dict[str, set[str]],
    entry_points: list[str] | None = None,
) -> list[str]:
    """Return modules in dependency-first order.

    Entry-point modules are moved to the end so that library code is
    always defined before the scripts that use it.  When entry points
    depend on each other, dependency order is respected; for independent
    entry points, the caller-provided order is preserved.
    """
    sorter = TopologicalSorter(graph)
    try:
        order = list(sorter.static_order())
    except CycleError as exc:
        cycle = exc.args[1]
        raise ValueError(
            "Circular dependency detected: "
            + " -> ".join(str(m) for m in cycle)
            + "\nrep2nb cannot resolve circular imports. "
            "Please refactor to break the cycle."
        ) from None

    if entry_points:
        ep_set = set(entry_points)
        non_ep = [m for m in order if m not in ep_set]
        ep_ordered = _stable_topo_sort(entry_points, graph, ep_set)
        return non_ep + ep_ordered

    return order


def _stable_topo_sort(
    modules: list[str],
    graph: dict[str, set[str]],
    module_set: set[str],
) -> list[str]:
    """Topological sort that uses *modules* list order as tiebreaker.

    For independent nodes the original position in *modules* is
    preserved; for dependent nodes the dependency constraint wins.
    """
    priority = {m: i for i, m in enumerate(modules)}

    in_deg: dict[str, int] = {m: 0 for m in modules}
    successors: dict[str, list[str]] = {m: [] for m in modules}
    for m in modules:
        for dep in graph.get(m, set()) & module_set:
            in_deg[m] += 1
            successors[dep].append(m)

    heap = [(priority[m], m) for m in modules if in_deg[m] == 0]
    heapq.heapify(heap)

    result: list[str] = []
    while heap:
        _, m = heapq.heappop(heap)
        result.append(m)
        for succ in successors[m]:
            in_deg[succ] -= 1
            if in_deg[succ] == 0:
                heapq.heappush(heap, (priority[succ], succ))

    return result
