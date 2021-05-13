from pathlib import Path

import pytest
from virtool.fake.factory import TestCaseDataFactory
from virtool.fake.json import VirtoolJsonObjectGroup


@pytest.fixture
def factory(app):
    return TestCaseDataFactory(app)


async def test_data_dump(factory, tmpdir, data_regression):
    ref = await factory.reference()

    objects = VirtoolJsonObjectGroup()

    objects.references.append(ref)

    data_path = Path(tmpdir) / "virtool_data"

    data_path.mkdir()

    await objects.dump(data_path)

    assert (data_path/"references").exists()

    loaded_objects = await objects.load(data_path)

    for produced, loaded in zip(objects, loaded_objects):
        assert produced == loaded
