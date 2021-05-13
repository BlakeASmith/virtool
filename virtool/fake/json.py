import datetime
from dateutil import parser
import json
from dataclasses import astuple, dataclass, field, fields
from itertools import chain
from pathlib import Path
from typing import (Any, Generic, List, Protocol, Type, TypeVar,
                    runtime_checkable)

import aiofiles

K = TypeVar("K")


@runtime_checkable
class JsonSerializer(Protocol, Generic[K]):

    @classmethod
    def __to_json__(cls, obj: K) -> str:
        ...

    @classmethod
    def __from_json__(cls, json_str: str) -> K:
        ...


def tojson(obj: Any, serailzer: Type[JsonSerializer] = None) -> str:
    try:
        return serailzer.__to_json__(obj)
    except (AttributeError, TypeError):
        return json.dumps(obj)


def fromjson(json_str: str, cls: Type[JsonSerializer] = None) -> Any:
    if not cls:
        return json.loads(json_str)
    return cls.__from_json__(json_str)


async def dump(obj: JsonSerializer, path: Path):
    async with aiofiles.open(path, "w") as f:
        await f.write(tojson(obj))


async def load(path: Path, cls: Type[JsonSerializer] = None):
    async with aiofiles.open(path, "w") as f:
        return fromjson(f.read(), cls)


class VirtoolCollectionSerializer(JsonSerializer[List[dict]]):

    @classmethod
    def __to_json__(cls, lst: List[dict]):
        lst = [
            {k: str(v) if isinstance(v, datetime.datetime) else v
             for k, v in obj.items()}
            for obj in lst
        ]

        return json.dumps(lst)

    @classmethod
    def __from_json__(cls, json_str: str):
        lst = json.loads(json_str)

        for obj in lst:
            for key in ("timestamp", "created_at"):
                if key in obj:
                    obj[key] = parser.parse(obj[key])

        return lst


@dataclass
class VirtoolJsonObjectGroup:
    analyses: List[dict] = field(default_factory=list)
    hmms: List[dict] = field(default_factory=list)
    indexes: List[dict] = field(default_factory=list)
    otus: List[dict] = field(default_factory=list)
    references: List[dict] = field(default_factory=list)
    samples: List[dict] = field(default_factory=list)

    def __iter__(self):
        return chain(astuple(self))

    async def dump(self, directory: Path):
        for collection in fields(self):
            async with aiofiles.open(directory/collection.name, "w") as f:
                json_target = getattr(self, collection.name)
                await f.write(
                    tojson(
                        json_target,
                        VirtoolCollectionSerializer
                    )
                )

    @classmethod
    async def load(cls, directory: Path) -> "VirtoolJsonObjectGroup":
        objects = VirtoolJsonObjectGroup()
        for collection in fields(objects):
            async with aiofiles.open(directory/collection.name, "r") as f:
                setattr(objects,
                        collection.name,
                        fromjson(
                            await f.read(),
                            VirtoolCollectionSerializer
                        ))

        return objects
