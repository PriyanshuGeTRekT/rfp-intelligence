"""Field definitions loaded from config/fields.yaml."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from rfp_intel.facts.models import FactKind

FieldType = Literal["identifier", "datetime", "duration", "text", "list", "summary"]


class FieldSpec(BaseModel):
    key: str
    name: str
    group: str
    type: FieldType
    description: str
    fact_types: list[str] = Field(default_factory=list)
    fact_kinds: list[FactKind] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    doc_types: list[str] = Field(default_factory=list)  # searched once more, filtered to these
    reconcile: bool = False
    enrich: bool = False  # reconciled date fields the model still describes (place, mandatory)
    diverse: bool = False  # items come from many documents: spread the evidence across them
    rerank_queries: bool = False  # rerank against each query too, not only the description


class FieldCatalog(BaseModel):
    groups: dict[str, str]
    fields: list[FieldSpec]

    @model_validator(mode="after")
    def _check(self) -> "FieldCatalog":
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate field keys")
        unknown = {f.group for f in self.fields} - set(self.groups) - {"report"}
        if unknown:
            raise ValueError(f"fields use undeclared groups: {sorted(unknown)}")
        return self

    def by_key(self, key: str) -> FieldSpec:
        return next(f for f in self.fields if f.key == key)

    def group(self, name: str) -> list[FieldSpec]:
        return [f for f in self.fields if f.group == name]

    @property
    def extraction_groups(self) -> list[str]:
        return list(self.groups)


@lru_cache(maxsize=4)
def load_fields(path: Path) -> FieldCatalog:
    with path.open(encoding="utf-8") as fh:
        return FieldCatalog.model_validate(yaml.safe_load(fh))
