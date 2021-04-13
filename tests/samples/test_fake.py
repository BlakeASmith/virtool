import pytest
from pprint import pprint
from virtool.samples.fake import create_fake_sample
from virtool.fake.wrapper import FakerWrapper
from virtool.samples.db import LIST_PROJECTION


@pytest.mark.parametrize("paired", [True, False])
@pytest.mark.parametrize("finalized", [True, False])
async def test_create_fake_unpaired(
    paired, finalized, dbi, pg, snapshot, run_in_thread, tmpdir
):
    app = {
        "db": dbi,
        "fake": FakerWrapper(),
        "pg": pg,
        "run_in_thread": run_in_thread,
        "data_path": str(tmpdir),
    }

    fake_sample = await create_fake_sample(app, paired=paired, finalized=finalized)

    for key in LIST_PROJECTION:
        assert key in fake_sample

    del fake_sample["created_at"]
    for f in fake_sample["files"]:
        del f["uploaded_at"]

    if finalized is True:
        assert len(fake_sample["files"]) == (2 if paired else 1)
        assert fake_sample["ready"] is True

        for f in fake_sample["reads"]:
            del f["uploaded_at"]

    snapshot.assert_match(fake_sample)
