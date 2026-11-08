"""Deterministic question, SQL and schema cues shared by the verifiers.

These helpers read text only. They never open a database or call a model, so the
verifiers stay usable offline and inside unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from src.db import _mask_literals_and_comments

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUM = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
_RANK_WORDS = r"(?:top|best|worst|bottom|highest|lowest|largest|smallest|biggest|greatest)"
_TOP_N_PATTERNS = (
    re.compile(rf"\b{_RANK_WORDS}\s+{_NUM}\b"),
    re.compile(rf"\b{_NUM}\s+(?:most|least|{_RANK_WORDS[3:-1]})\b"),
)
# "at least 2 orders" is a filter, not a request for the minimum.
_HEDGES = re.compile(r"\bat (?:least|most)\b|\bno (?:more|less|fewer) than\b")
_MAX = re.compile(
    r"\b(?:highest|most|maximum|max|largest|biggest|greatest|top|best|oldest|"
    r"latest|longest|heaviest|tallest|newest)\b"
)
_MIN = re.compile(
    r"\b(?:lowest|least|minimum|min|smallest|fewest|bottom|worst|youngest|"
    r"earliest|shortest|lightest|cheapest)\b"
)
_COUNT = re.compile(r"\bhow many\b|\bnumber of\b|\bcount\b|\btotal (?:number|count)\b")
_AVERAGE = re.compile(r"\b(?:average|avg|mean)\b")
_SUM = re.compile(r"\b(?:total|sum|how much)\b")
_MONEY = re.compile(
    r"\b(?:spend|spending|spent|amounts?|revenue|sales|prices?|costs?|paid|payments?|"
    r"salar(?:y|ies)|income|earnings?|value|fees?)\b"
)
_GROUPED = re.compile(r"\b(?:per|each|every|by|breakdown|across|grouped)\b")
_SCALAR = re.compile(
    r"^(?:how many|how much|count\b|what(?: is|'s| was) the "
    r"(?:total|average|mean|number|count|sum)\b)"
)


@dataclass(frozen=True)
class QuestionIntent:
    """Ranking and aggregation cues stated in a natural-language question."""

    top_n: int | None
    wants_count: bool
    wants_average: bool
    wants_sum: bool
    sums_quantity: bool  # "total spending": a measured value that must be SUMmed, not counted
    wants_max: bool
    wants_min: bool
    grouped: bool
    expects_scalar: bool

    @property
    def wants_aggregate(self) -> bool:
        return self.wants_count or self.wants_average or self.wants_sum


def normalize_question(question: str) -> str:
    return " ".join(question.lower().strip().rstrip("?!.").split())


def parse_intent(question: str) -> QuestionIntent:
    """Extract the cues a correct SQL answer and result should reflect."""
    text = normalize_question(question)
    top_n = None
    for pattern in _TOP_N_PATTERNS:
        match = pattern.search(text)
        if match:
            token = match.group(1)
            top_n = int(token) if token.isdigit() else _NUMBER_WORDS[token]
            break
    unhedged = _HEDGES.sub(" ", text)
    wants_count = bool(_COUNT.search(text))
    wants_sum = bool(_SUM.search(re.sub(r"\btotal (?:number|count)\b", " ", text)))
    grouped = bool(_GROUPED.search(text))
    return QuestionIntent(
        top_n=top_n,
        wants_count=wants_count,
        wants_average=bool(_AVERAGE.search(text)),
        wants_sum=wants_sum,
        sums_quantity=wants_sum and bool(_MONEY.search(text)),
        wants_max=bool(_MAX.search(unhedged)),
        wants_min=bool(_MIN.search(unhedged)),
        grouped=grouped,
        expects_scalar=bool(_SCALAR.search(text)) and not grouped and top_n is None,
    )


@dataclass(frozen=True)
class SqlFeatures:
    """Clauses and aggregates present in a SELECT statement."""

    has_count: bool
    has_sum: bool
    has_avg: bool
    has_max: bool
    has_min: bool
    has_order: bool
    order_desc: bool
    has_division: bool
    has_distinct: bool
    limit: int | None
    aliases: frozenset[str]


_ALIAS = re.compile(
    r"\bAS\s+(?:\"([^\"]+)\"|`([^`]+)`|\[([^\]]+)\]|'([^']+)'|(\w+))", re.IGNORECASE
)


def parse_sql(sql: str) -> SqlFeatures:
    """Read aggregates, ordering and LIMIT from SQL with literals masked out."""
    try:
        masked = _mask_literals_and_comments(sql)
    except ValueError:
        masked = sql
    upper = masked.upper()
    order = re.search(r"\bORDER\s+BY\b(.*?)(?:\bLIMIT\b|$)", upper, re.DOTALL)
    limit = re.search(r"\bLIMIT\s+(\d+)", upper)
    aliases = frozenset(
        next(group for group in match.groups() if group).lower()
        for match in _ALIAS.finditer(sql)
    )
    return SqlFeatures(
        has_count=bool(re.search(r"\bCOUNT\s*\(", upper)),
        has_sum=bool(re.search(r"\b(?:SUM|TOTAL)\s*\(", upper)),
        has_avg=bool(re.search(r"\bAVG\s*\(", upper)),
        has_max=bool(re.search(r"\bMAX\s*\(", upper)),
        has_min=bool(re.search(r"\bMIN\s*\(", upper)),
        has_order=order is not None,
        order_desc=bool(order and re.search(r"\bDESC\b", order.group(1))),
        has_division="/" in upper,
        has_distinct=bool(re.search(r"\bDISTINCT\b", upper)),
        limit=int(limit.group(1)) if limit else None,
        aliases=aliases,
    )


@dataclass(frozen=True)
class SchemaInfo:
    """Tables and columns named in a textual schema context."""

    tables: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def columns(self) -> set[str]:
        return {column.lower() for columns in self.tables.values() for column in columns}

    @property
    def tokens(self) -> set[str]:
        """Lower-case words from every table and column name, plus singular forms."""
        words: set[str] = set()
        for name in [*self.tables, *(c for cols in self.tables.values() for c in cols)]:
            snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()
            parts = [part for part in re.split(r"[^a-z0-9]+", snake) if part]
            words.update(parts)
            words.add("".join(parts))
        return words | {_singular(word) for word in words}


_TABLE_START = re.compile(r"^\s*TABLE\s+(\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|\S+)\s*\(", re.IGNORECASE)
_COLUMN = re.compile(r"^\s*(\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|\w+)")
_COMPACT = re.compile(r"^\s*(\w+)\s*\(([^()]*)\)\s*$")
_CONSTRAINT = re.compile(r"^\s*(?:FOREIGN|PRIMARY|UNIQUE|CONSTRAINT|CHECK)\b", re.IGNORECASE)


def _unquote(name: str) -> str:
    return name[1:-1] if name[:1] in "\"`[" else name


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def parse_schema(schema_context: str) -> SchemaInfo:
    """Parse the TABLE blocks produced by the flat and Neo4j retrievers.

    Lines beginning with ``--`` are retriever notes (for example a fallback
    explanation) and are kept separately rather than read as tables.
    """
    info = SchemaInfo()
    current: str | None = None
    for line in schema_context.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            info.notes.append(stripped.lstrip("- ").strip())
            continue
        start = _TABLE_START.match(line)
        if start:
            current = _unquote(start.group(1))
            info.tables[current] = []
            continue
        if current is None:
            compact = _COMPACT.match(line)
            if compact:
                info.tables[compact.group(1)] = [
                    _unquote(part.strip().split()[0]) for part in compact.group(2).split(",") if part.strip()
                ]
            continue
        if stripped.startswith(")"):
            current = None
            continue
        if _CONSTRAINT.match(line):
            continue
        column = _COLUMN.match(line)
        if column:
            info.tables[current].append(_unquote(column.group(1)))
    return info


# Question wording that needs a specific kind of data, and the schema words that
# would provide it. The first item is the name reported in missing_fields.
_CONCEPTS: tuple[tuple[re.Pattern[str], str, frozenset[str]], ...] = tuple(
    (re.compile(pattern), label, frozenset(words))
    for pattern, label, words in (
        (r"\bprofits?\b|\bmargins?\b", "cost",
         {"cost", "costs", "cogs", "expense", "expenses", "profit", "margin", "unitcost"}),
        (r"\bcategor(?:y|ies)\b", "category",
         {"category", "genre", "segment", "department"}),
        (r"\bregions?\b|\bterritor(?:y|ies)\b", "region",
         {"region", "territory", "country", "state", "city", "location", "area"}),
        (r"\bdiscounts?\b", "discount", {"discount", "promo", "promotion", "coupon"}),
        (r"\bratings?\b|\breviews?\b", "rating", {"rating", "review", "score", "star", "stars"}),
        (r"\bquantit(?:y|ies)\b|\bunits sold\b", "quantity", {"quantity", "qty", "unit", "units"}),
        (r"\bsalar(?:y|ies)\b|\bwages?\b", "salary", {"salary", "wage", "pay", "income", "compensation"}),
        (r"\bgender\b", "gender", {"gender", "sex"}),
        (r"\bphone\b|\btelephone\b", "phone", {"phone", "telephone", "mobile", "cell"}),
        (r"\bages?\b|\bhow old\b", "age", {"age", "birth", "birthday", "birthdate", "dob", "born", "year"}),
        (r"\brevenue\b|\bsales\b|\bspend(?:ing)?\b|\bspent\b", "revenue",
         {"amount", "price", "revenue", "sales", "sale", "total", "payment", "spend",
          "spending", "fee", "value", "charge", "earning", "earnings"}),
    )
)


def missing_concepts(question: str, schema: SchemaInfo) -> list[str]:
    """Return data the question asks about that no schema table or column provides."""
    text = normalize_question(question)
    tokens = schema.tokens
    return [label for pattern, label, words in _CONCEPTS if pattern.search(text) and not tokens & words]
