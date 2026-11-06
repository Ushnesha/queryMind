"""Deterministic question-only ranking and FK paths; no gold SQL or LLM calls."""

from collections import Counter, deque
from itertools import combinations
import math
import re
from typing import Any

_STOPWORDS = frozenset(
    "a an the and or of to for from in on at by with as is are was were be been "
    "what which who how many much list show find give get all each their that "
    "have has had do does did most least more less than number total average "
    "maximum minimum highest lowest order sort ascending descending distinct "
    "please name names id ids".split()
)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def terms(text: str) -> set[str]:
    """Split SQL identifiers and ordinary words with conservative plural folding."""
    separated = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return {_stem(word) for word in re.findall(r"[a-z]+|\d+", separated.lower())
            if word not in _STOPWORDS}


def rank_tables(payload: dict[str, Any], question: str, top_k: int) -> list[str]:
    """Return at most top_k lexical anchors, downweighting ubiquitous columns.

    The rule is fixed across databases and sees only question/schema identifiers.
    Tables receive stronger weight than columns. Weak incidental matches are
    dropped relative to the best score. All columns of selected tables survive.
    """
    if top_k < 1:
        raise ValueError("top_k must be positive.")
    query = terms(question)
    table_terms = {t["name"]: terms(t["name"]) for t in payload["tables"]}
    column_terms = {t["name"]: set().union(*(terms(c["name"]) for c in t["columns"]))
                    if t["columns"] else set() for t in payload["tables"]}
    frequencies = Counter(term for name in table_terms for term in table_terms[name] | column_terms[name])
    count = max(len(table_terms), 1)
    ranked: list[tuple[float, str]] = []
    for name in table_terms:
        score = sum(4.0 * (1 + math.log((count + 1) / (frequencies[t] + 1)))
                    for t in query & table_terms[name])
        score += sum(1 + math.log((count + 1) / (frequencies[t] + 1))
                     for t in (query & column_terms[name]) - table_terms[name])
        if score:
            ranked.append((score, name))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked:
        return []
    threshold = ranked[0][0] * 0.25
    return [name for score, name in ranked if score >= threshold][:top_k]


def expand_local_join_paths(payload: dict[str, Any], table_names: list[str]) -> list[str]:
    """Diagnostic BFS closure over shortest FK paths for every anchor pair.

    Intermediate bridge tables may exceed top_k. Disconnected components are
    retained without invented links. The live implementation uses Neo4j's own
    shortestPath operation rather than this helper.
    """
    adjacent: dict[str, set[str]] = {t["name"]: set() for t in payload["tables"]}
    for edge in payload["relationships"]:
        adjacent[edge["from_table"]].add(edge["to_table"])
        adjacent[edge["to_table"]].add(edge["from_table"])
    selected = set(table_names)
    for source, target in combinations(sorted(selected), 2):
        paths = deque([[source]])
        visited = {source}
        while paths:
            path = paths.popleft()
            if path[-1] == target:
                selected.update(path)
                break
            for neighbor in sorted(adjacent[path[-1]] - visited):
                visited.add(neighbor)
                paths.append(path + [neighbor])
    return sorted(selected)
