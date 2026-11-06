"""Topic labels (deadline, delivery, warranty, ...) for facts, driven by config/fact_types.yaml."""

import re
from functools import cached_property, lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from rfp_intel.facts.models import FactKind


class TypeRule(BaseModel):
    kinds: list[FactKind] | None = None
    cues: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    always: bool = False

    @cached_property
    def cue_res(self) -> list[re.Pattern[str]]:
        return [re.compile(p, re.I) for p in self.cues]

    @cached_property
    def exclude_res(self) -> list[re.Pattern[str]]:
        return [re.compile(p, re.I) for p in self.exclude]

    def applies_to(self, kind: FactKind) -> bool:
        return self.kinds is None or kind in self.kinds


class FactTypeConfig(BaseModel):
    types: dict[str, TypeRule]


@lru_cache(maxsize=8)
def load_fact_types(path: Path) -> FactTypeConfig:
    with path.open(encoding="utf-8") as fh:
        return FactTypeConfig.model_validate(yaml.safe_load(fh))


def _match(rules: dict[str, TypeRule], kind: FactKind, text: str, scope: str) -> list[str]:
    found: list[str] = []
    for name, rule in rules.items():
        if not rule.applies_to(kind) or rule.always:
            continue
        if any(rx.search(text) for rx in rule.cue_res) and not any(
            rx.search(scope) for rx in rule.exclude_res
        ):
            found.append(name)
    return found


def route(config: FactTypeConfig, query: str) -> list[str]:
    """Topic labels a question is about, using the same cues as the facts themselves.

    "When are proposals due?" routes to deadline; "When are questions due?" routes to
    questions only, because the deadline label excludes question contexts.
    """
    return [
        name
        for name, rule in config.types.items()
        if not rule.always
        and any(rx.search(query) for rx in rule.cue_res)
        and not any(rx.search(query) for rx in rule.exclude_res)
    ]


def label(
    config: FactTypeConfig,
    kind: FactKind,
    context: str,
    *,
    section: str | None = None,
    scope_extra: str = "",
    neighbours: str = "",
) -> list[str]:
    """Labels for one fact: from its own context, else its neighbours, else its section.

    `neighbours` is nearby text that names a value with a generic label, e.g. "Event Type:
    Prebid Conference" just above "Event date: 06/10/2024".
    """
    labels = [n for n, r in config.types.items() if r.always and r.applies_to(kind)]
    scope = f"{context}\n{scope_extra}"
    found = _match(config.types, kind, context, scope)
    if not found and neighbours:
        found = _match(config.types, kind, neighbours, f"{scope}\n{neighbours}")
    if not found and section:
        found = _match(config.types, kind, section, f"{scope}\n{section}")
    return labels + found
