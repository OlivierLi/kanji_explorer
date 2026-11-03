"""Deterministic component reachability shared by ETL and offline search."""
from collections import deque
from collections.abc import Iterable, Mapping
from typing import NamedTuple


class ComponentPath(NamedTuple):
    min_depth: int
    is_direct: int
    via_char: str


class ComponentGraph:
    """Primary descendants with primary/alternative first-level components.

    Alternative decompositions contribute direct edges at the queried root;
    subsequent traversal follows primary decompositions, matching the ETL policy.
    Source mappings are copied so later caller mutations cannot change the graph.
    """

    def __init__(self, primary: Mapping[str, Iterable[str]],
                 alternatives: Mapping[str, Iterable[str]] | None = None):
        self.primary = {char: tuple(sorted(set(children) - {char}))
                        for char, children in primary.items()}
        self.alternatives = {char: tuple(sorted(set(children) - {char}))
                             for char, children in (alternatives or {}).items()}

    def closure(self, target: str, max_depth: int = 6) -> dict[str, ComponentPath]:
        if max_depth < 1:
            return {}
        # Seed *all* direct edges before walking. An alternative direct edge
        # must not be hidden by an earlier indirect primary path.
        direct = sorted(set(self.primary.get(target, ())) |
                        set(self.alternatives.get(target, ())))
        paths = {char: ComponentPath(1, 1, '') for char in direct}
        queue = deque((char, char) for char in direct)
        while queue:
            char, via = queue.popleft()
            depth = paths[char].min_depth
            if depth >= max_depth:
                continue
            for child in self.primary.get(char, ()):
                if child == target or child in paths:
                    continue
                paths[child] = ComponentPath(depth + 1, 0, via)
                queue.append((child, via))
        return paths

    def reverse_index(self, targets: Iterable[str]) -> dict[str, dict[str, ComponentPath]]:
        """Index complete paths before callers filter or truncate result lists."""
        result: dict[str, dict[str, ComponentPath]] = {}
        for target in sorted(set(targets)):
            for component, path in self.closure(target).items():
                result.setdefault(component, {})[target] = path
        return result
