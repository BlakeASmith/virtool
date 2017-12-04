import arrow
import logging
import os

import virtool.utils

logger = logging.getLogger(__name__)


PROJECTION = [
    "_id",
    "name",
    "size",
    "user",
    "uploaded_at",
    "type",
    "ready",
    "reserved"
]


async def create(db, dispatch, filename, file_type, user_id=None):
    file_id = None

    while file_id is None or file_id in await db.files.distinct("_id"):
        file_id = "{}-{}".format(await virtool.utils.get_new_id(db.files), filename)

    uploaded_at = virtool.utils.timestamp()

    expires_at = None

    if file_type == "viruses":
        expires_at = arrow.get(uploaded_at).shift(hours=+5).datetime

    user = None

    if user_id is not None:
        user = {
            "id": user_id
        }

    document = {
        "_id": file_id,
        "name": filename,
        "type": file_type,
        "user": user,
        "uploaded_at": uploaded_at,
        "expires_at": expires_at,
        "created": False,
        "reserved": False,
        "ready": False
    }

    await db.files.insert_one(document)

    # Return document will all keys, but size.
    document = {key: document[key] for key in [key for key in PROJECTION if key != "size"]}

    document = virtool.utils.base_processor(document)

    await dispatch(
        "files",
        "update",
        document
    )

    return document


async def reserve(db, dispatch, file_ids):
    await db.files.update_many({"_id": {"$in": file_ids}}, {
        "$set": {
            "reserved": True
        }
    })

    async for document in db.files.find({"_id": {"$in": file_ids}}, PROJECTION):
        await dispatch(
            "files",
            "update",
            virtool.utils.base_processor(document)
        )


async def release_reservations(db, dispatch, file_ids):
    await db.files.update_many({"_id": {"$in": file_ids}}, {
        "$set": {
            "reserve": False
        }
    })

    async for document in db.files.find({"_id": {"$in": file_ids}}, PROJECTION):
        await dispatch(
            "files",
            "update",
            virtool.utils.base_processor(document)
        )


async def remove(loop, db, settings, dispatch, file_id):
    await db.files.delete_one({"_id": file_id})

    await dispatch("files", "remove", [file_id])

    file_path = os.path.join(settings.get("data_path"), "files", file_id)

    await loop.run_in_executor(None, virtool.utils.rm, file_path)
