from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List

from schema_agent.core.planner.postgres import Step


def schedule_steps(steps: List[Step]) -> List[Step]:
    # simple topological sort by depends_on
    id_to_step: Dict[str, Step] = {s.id: s for s in steps}
    graph: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {s.id: 0 for s in steps}

    for s in steps:
        for d in s.depends_on:
            graph[d].append(s.id)
            indeg[s.id] += 1

    q = deque([sid for sid, deg in indeg.items() if deg == 0])
    ordered: List[Step] = []
    while q:
        sid = q.popleft()
        ordered.append(id_to_step[sid])
        for nxt in graph.get(sid, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)

    # if cycles, fallback to original order
    if len(ordered) != len(steps):
        return steps

    # Preserve topological order strictly to honor dependencies
    return ordered


