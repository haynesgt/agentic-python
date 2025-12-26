import json
from collections.abc import Iterable

from pydantic import BaseModel


def dumps(models: Iterable[BaseModel]) -> str:
    return json.dumps(
        [m.model_dump(mode="json") for m in models],
        ensure_ascii=False,
    )
