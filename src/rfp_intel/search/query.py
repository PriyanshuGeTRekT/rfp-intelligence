"""Query understanding: identifiers, topic routing and synonym expansion. No LLM involved."""

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from rfp_intel.facts.labels import FactTypeConfig, route
from rfp_intel.facts.patterns import find_identifiers
from rfp_intel.search.models import QueryAnalysis


class Synonyms(BaseModel):
    groups: list[list[str]]

    def expand(self, query: str) -> list[str]:
        """Phrases to add: the rest of every group that has a phrase in the query."""
        added: list[str] = []
        lowered = query.lower()
        for group in self.groups:
            if any(re.search(rf"(?<!\w){re.escape(p.lower())}(?!\w)", lowered) for p in group):
                added.extend(p for p in group if p.lower() not in lowered and p not in added)
        return added


@lru_cache(maxsize=8)
def load_synonyms(path: Path) -> Synonyms:
    with path.open(encoding="utf-8") as fh:
        return Synonyms.model_validate(yaml.safe_load(fh))


def query_identifiers(query: str) -> list[str]:
    """Identifier-shaped tokens in a question, in both written and compact form.

    The query is upper-cased first so "wd22tb4" matches the indexed "WD22TB4".
    """
    found: list[str] = []
    for m in find_identifiers(query.upper(), []):
        for form in (m.value["id"], m.value["compact"]):
            if form not in found:
                found.append(form)
    return found


def analyze(
    query: str, fact_config: FactTypeConfig, synonyms: Synonyms | None, *, expand: bool = True
) -> QueryAnalysis:
    expansions = synonyms.expand(query) if synonyms and expand else []
    sparse_query = " ".join([query, *expansions])
    return QueryAnalysis(
        query=query,
        identifiers=query_identifiers(query),
        fact_types=route(fact_config, query),
        sparse_query=sparse_query,
        expansions=expansions,
    )
