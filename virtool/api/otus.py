from copy import deepcopy

import pymongo.errors
from aiohttp import web

import virtool.db.history
import virtool.db.otus
import virtool.db.references
import virtool.db.utils
import virtool.history
import virtool.http.routes
import virtool.otus
import virtool.references
import virtool.utils
import virtool.validators
from virtool.api.utils import bad_request, conflict, json_response, no_content, not_found

SCHEMA_VALIDATOR = {
    "type": "list",
    "validator": virtool.validators.has_unique_segment_names,
    "schema": {
        "type": "dict",
        "allow_unknown": False,
        "schema": {
            "name": {"type": "string", "required": True},
            "required": {"type": "boolean", "default": True},
            "molecule": {"type": "string", "default": "", "allowed": [
                "",
                "ssDNA",
                "dsDNA",
                "ssRNA",
                "ssRNA+",
                "ssRNA-",
                "dsRNA"
            ]}
        }
    }
}

routes = virtool.http.routes.Routes()


@routes.get("/api/otus")
async def find(req):
    """
    Find otus.

    """
    db = req.app["db"]

    term = req["query"].get("find", None)
    verified = req["query"].get("verified", None)
    names = req["query"].get("names", False)

    data = await virtool.db.otus.find(
        db,
        names,
        term,
        req["query"],
        verified
    )

    return json_response(data)


@routes.get("/api/otus/{otu_id}")
async def get(req):
    """
    Get a complete otu document. Joins the otu document with its associated sequence documents.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    complete = await virtool.db.otus.join_and_format(db, otu_id)

    if not complete:
        return not_found()

    return json_response(complete)


@routes.post("/api/refs/{ref_id}/otus", schema={
    "name": {"type": "string", "required": True, "minlength": 1},
    "abbreviation": {"type": "string", "default": ""},
    "schema": SCHEMA_VALIDATOR
})
async def create(req):
    """
    Add a new otu to the collection. Checks to make sure the supplied otu name and abbreviation are not already in
    use in the collection. Any errors are sent back to the client.

    """
    db = req.app["db"]
    data = req["data"]

    ref_id = req.match_info["ref_id"]

    # Check if either the name or abbreviation are already in use. Send a ``409`` to the client if there is a conflict.
    message = await virtool.db.otus.check_name_and_abbreviation(db, ref_id, data["name"], data["abbreviation"])

    if message:
        return conflict(message)

    joined = await virtool.db.otus.create(db, ref_id, data["name"], data["abbreviation"])

    description = virtool.history.compose_create_description(joined)

    change = await virtool.db.history.add(
        db,
        "create",
        None,
        joined,
        description,
        req["client"].user_id
    )

    formatted = virtool.otus.format_otu(joined, most_recent_change=change)

    headers = {
        "Location": "/api/otus/" + formatted["id"]
    }

    return json_response(formatted, status=201, headers=headers)


@routes.patch("/api/otus/{otu_id}", schema={
    "name": {"type": "string", "minlength": 1},
    "abbreviation": {"type": "string"},
    "schema": SCHEMA_VALIDATOR
})
async def edit(req):
    """
    Edit an existing OTU. Checks to make sure the supplied OTU name and abbreviation are not already in use in
    the collection.

    """
    db = req.app["db"]
    data = req["data"]

    otu_id = req.match_info["otu_id"]

    # Get existing complete otu record, at the same time ensuring it exists. Send a ``404`` if not.
    old = await virtool.db.otus.join(db, otu_id)

    if not old:
        return not_found()

    ref_id = old["reference"]["id"]

    name, abbreviation, schema = virtool.otus.evaluate_changes(data, old)

    # Send ``200`` with the existing otu record if no change will be made.
    if name is None and abbreviation is None and schema is None:
        return json_response(await virtool.db.otus.join_and_format(db, otu_id))

    # Make sure new name or abbreviation are not already in use.
    message = await virtool.db.otus.check_name_and_abbreviation(db, ref_id, name, abbreviation)

    if message:
        return json_response({"message": message}, status=409)

    # Update the ``modified`` and ``verified`` fields in the otu document now, because we are definitely going to
    # modify the otu.
    data["verified"] = False

    # If the name is changing, update the ``lower_name`` field in the otu document.
    if name:
        data["lower_name"] = name.lower()

    # Update the database collection.
    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": data,
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.update_verification(db, new)

    description = virtool.history.compose_edit_description(name, abbreviation, old["abbreviation"], schema)

    await virtool.db.history.add(
        db,
        "edit",
        old,
        new,
        description,
        req["client"].user_id
    )

    return json_response(await virtool.db.otus.join_and_format(db, otu_id, joined=new, issues=issues))


@routes.delete("/api/otus/{otu_id}")
async def remove(req):
    """
    Remove an OTU document and its associated sequence documents.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    removed = await virtool.db.otus.remove(
        db,
        otu_id,
        req["client"].user_id
    )

    if removed is None:
        return not_found()

    return web.Response(status=204)


@routes.get("/api/otus/{otu_id}/isolates")
async def list_isolates(req):
    """
    Return a list of isolate records for a given otu.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    document = await virtool.db.otus.join_and_format(db, otu_id)

    if not document:
        return not_found()

    return json_response(document["isolates"])


@routes.get("/api/otus/{otu_id}/isolates/{isolate_id}")
async def get_isolate(req):
    """
    Get a complete specific isolate sub-document, including its sequences.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.otus.find_one({"_id": otu_id, "isolates.id": isolate_id}, ["isolates"])

    if not document:
        return not_found()

    isolate = dict(virtool.otus.find_isolate(document["isolates"], isolate_id), sequences=[])

    async for sequence in db.sequences.find({"isolate_id": isolate_id}, {"otu_id": False, "isolate_id": False}):
        sequence["id"] = sequence.pop("_id")
        isolate["sequences"].append(sequence)

    return json_response(isolate)


@routes.post("/api/otus/{otu_id}/isolates", schema={
    "source_type": {"type": "string", "default": ""},
    "source_name": {"type": "string", "default": ""},
    "default": {"type": "boolean", "default": False}
})
async def add_isolate(req):
    """
    Add a new isolate to a otu.

    """
    db = req.app["db"]
    data = req["data"]
    settings = req.app["settings"]

    otu_id = req.match_info["otu_id"]

    document = await db.otus.find_one(otu_id)

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    # True if the new isolate should be default and any existing isolates should be non-default.
    will_be_default = not isolates or data["default"]

    # Get the complete, joined entry before the update.
    old = await virtool.db.otus.join(db, otu_id, document)

    # All source types are stored in lower case.
    data["source_type"] = data["source_type"].lower()

    if not await virtool.db.references.check_source_type(db, document["reference"]["id"], data["source_type"]):
        return conflict("Source type is not allowed")

    # Get a unique isolate_id for the new isolate.
    isolate_id = await virtool.db.otus.get_new_isolate_id(db)

    # Set ``default`` to ``False`` for all existing isolates if the new one should be default.
    if isolates and data["default"]:
        for isolate in isolates:
            isolate["default"] = False

    # Force the new isolate as default if it is the first isolate.
    if not isolates:
        data["default"] = True

    # Set the isolate as the default isolate if it is the first one.
    data.update({
        "default": will_be_default,
        "id": isolate_id
    })

    isolates.append(data)

    # Push the new isolate to the database.
    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    # Get the joined entry now that it has been updated.
    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.verify(db, otu_id, joined=new)

    if issues is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.otus.format_isolate_name(data)

    description = "Added {}".format(isolate_name)

    if will_be_default:
        description += " as default"

    await virtool.db.history.add(
        db,
        "add_isolate",
        old,
        new,
        description,
        req["client"].user_id
    )

    headers = {
        "Location": "/api/otus/{}/isolates/{}".format(otu_id, isolate_id)
    }

    return json_response(dict(data, sequences=[]), status=201, headers=headers)


@routes.patch("/api/otus/{otu_id}/isolates/{isolate_id}", schema={
    "source_type": {"type": "string"},
    "source_name": {"type": "string"}
})
async def edit_isolate(req):
    """
    Edit an existing isolate.

    """
    db = req.app["db"]
    settings = req.app["settings"]
    data = req["data"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.otus.find_one({"_id": otu_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate = virtool.otus.find_isolate(isolates, isolate_id)

    if not isolate:
        return not_found()

    # All source types are stored in lower case.
    if "source_type" in data:
        data["source_type"] = data["source_type"].lower()

        if settings.get("restrict_source_types") and data["source_type"] not in settings.get("allowed_source_types"):
            return conflict("Not an allowed source type")

    old_isolate_name = virtool.otus.format_isolate_name(isolate)

    isolate.update(data)

    old = await virtool.db.otus.join(db, otu_id)

    # Replace the isolates list with the update one.
    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    # Get the joined entry now that it has been updated.
    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.verify(db, otu_id, joined=new)

    if issues is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.otus.format_isolate_name(isolate)

    # Use the old and new entry to add a new history document for the change.
    await virtool.db.history.add(
        db,
        "edit_isolate",
        old,
        new,
        "Renamed {} to {}".format(old_isolate_name, isolate_name),
        req["client"].user_id
    )

    complete = await virtool.db.otus.join_and_format(db, otu_id, joined=new)

    for isolate in complete["isolates"]:
        if isolate["id"] == isolate_id:
            return json_response(isolate, status=200)


@routes.put("/api/otus/{otu_id}/isolates/{isolate_id}/default", schema={
    "source_type": {"type": "string"},
    "source_name": {"type": "string"}
})
async def set_as_default(req):
    """
    Set an isolate as default.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.otus.find_one({"_id": otu_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate = virtool.otus.find_isolate(isolates, isolate_id)

    if not isolate:
        return not_found()

    # Set ``default`` to ``False`` for all existing isolates if the new one should be default.
    for existing_isolate in isolates:
        existing_isolate["default"] = False

    isolate["default"] = True

    if isolates == document["isolates"]:
        complete = await virtool.db.otus.join_and_format(db, otu_id)
        for isolate in complete["isolates"]:
            if isolate["id"] == isolate_id:
                return json_response(isolate)

    old = await virtool.db.otus.join(db, otu_id)

    # Replace the isolates list with the updated one.
    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    # Get the joined entry now that it has been updated.
    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.verify(db, otu_id, joined=new)

    if issues is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.otus.format_isolate_name(isolate)

    # Use the old and new entry to add a new history document for the change.
    await virtool.db.history.add(
        db,
        "set_as_default",
        old,
        new,
        "Set {} as default".format(isolate_name),
        req["client"].user_id
    )

    complete = await virtool.db.otus.join_and_format(db, otu_id, new)

    for isolate in complete["isolates"]:
        if isolate["id"] == isolate_id:
            return json_response(isolate)


@routes.delete("/api/otus/{otu_id}/isolates/{isolate_id}", schema={
    "source_type": {"type": "string"},
    "source_name": {"type": "string"}
})
async def remove_isolate(req):
    """
    Remove an isolate and its sequences from a otu.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    document = await db.otus.find_one(otu_id)

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate_id = req.match_info["isolate_id"]

    # Get any isolates that have the isolate id to be removed (only one should match!).
    isolate_to_remove = virtool.otus.find_isolate(isolates, isolate_id)

    if not isolate_to_remove:
        return not_found()

    # Remove the isolate from the otu' isolate list.
    isolates.remove(isolate_to_remove)

    new_default = None

    # Set the first isolate as default if the removed isolate was the default.
    if isolate_to_remove["default"] and len(isolates):
        new_default = isolates[0]
        new_default["default"] = True

    old = await virtool.db.otus.join(db, otu_id, document)

    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.verify(db, otu_id, joined=new)

    if issues is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    # Remove any sequences associated with the removed isolate.
    await db.sequences.delete_many({"isolate_id": isolate_id})

    description = "Removed {}".format(virtool.otus.format_isolate_name(isolate_to_remove))

    if isolate_to_remove["default"] and new_default:
        description += " and set {} as default".format(virtool.otus.format_isolate_name(new_default))

    await virtool.db.history.add(
        db,
        "remove_isolate",
        old,
        new,
        description,
        req["client"].user_id
    )

    return no_content()


@routes.get("/api/otus/{otu_id}/isolates/{isolate_id}/sequences")
async def list_sequences(req):
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]

    if not await db.otus.find({"_id": otu_id}, {"isolates.id": isolate_id}).count():
        return not_found()

    projection = list(virtool.db.otus.SEQUENCE_PROJECTION)

    projection.remove("otu_id")
    projection.remove("isolate_id")

    documents = await db.sequences.find({"isolate_id": isolate_id}, projection).to_list(None)

    return json_response([virtool.utils.base_processor(d) for d in documents])


@routes.get("/api/otus/{otu_id}/isolates/{isolate_id}/sequences/{sequence_id}")
async def get_sequence(req):
    """
    Get a single sequence document by its ``accession`.

    """
    db = req.app["db"]

    sequence_id = req.match_info["sequence_id"]

    document = await db.sequences.find_one(sequence_id, virtool.db.otus.SEQUENCE_PROJECTION)

    if not document:
        return not_found()

    return json_response(virtool.utils.base_processor(document))


@routes.post("/api/otus/{otu_id}/isolates/{isolate_id}/sequences", schema={
    "id": {"type": "string", "minlength": 1, "required": True},
    "definition": {"type": "string", "minlength": 1, "required": True},
    "host": {"type": "string"},
    "segment": {"type": "string"},
    "sequence": {"type": "string", "minlength": 1, "required": True}
})
async def create_sequence(req):
    """
    Create a new sequence record for the given isolate.

    """
    db, data = req.app["db"], req["data"]

    # Extract variables from URL path.
    otu_id, isolate_id = (req.match_info[key] for key in ["otu_id", "isolate_id"])

    # Get the subject otu document. Will be ``None`` if it doesn't exist. This will result in a ``404`` response.
    document = await db.otus.find_one({"_id": otu_id, "isolates.id": isolate_id})

    if not document:
        return not_found("otu or isolate not found")

    segment = data.get("segment", None)

    if segment and segment not in {s["name"] for s in document.get("schema", {})}:
        return not_found("Segment not found")

    # Update POST data to make sequence document.
    data.update({
        "_id": data.pop("id"),
        "otu_id": otu_id,
        "isolate_id": isolate_id,
        "host": data.get("host", ""),
        "segment": segment
    })

    old = await virtool.db.otus.join(db, otu_id, document)

    try:
        await db.sequences.insert_one(data)
    except pymongo.errors.DuplicateKeyError:
        return conflict("Sequence id already exists")

    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.otus.join(db, otu_id, document)

    issues = await virtool.db.otus.verify(db, otu_id, joined=new)

    if issues is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate = virtool.otus.find_isolate(old["isolates"], isolate_id)

    await virtool.db.history.add(
        db,
        "create_sequence",
        old,
        new,
        "Created new sequence {} in {}".format(data["_id"], virtool.otus.format_isolate_name(isolate)),
        req["client"].user_id
    )

    headers = {
        "Location": "/api/otus/{}/isolates/{}/sequences/{}".format(otu_id, isolate_id, data["_id"])
    }

    return json_response(virtool.utils.base_processor(data), status=201, headers=headers)


@routes.patch("/api/otus/{otu_id}/isolates/{isolate_id}/sequences/{sequence_id}", schema={
    "host": {"type": "string"},
    "definition": {"type": "string"},
    "segment": {"type": "string"},
    "sequence": {"type": "string"},
    "schema": {"type": "list"}
})
async def edit_sequence(req):
    db, data = req.app["db"], req["data"]

    if not len(data):
        return bad_request("Empty Input")

    otu_id, isolate_id, sequence_id = (req.match_info[key] for key in ["otu_id", "isolate_id", "sequence_id"])

    document = await db.otus.find_one({"_id": otu_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    old = await virtool.db.otus.join(db, otu_id, document)

    segment = data.get("segment", None)

    if segment and segment not in {s["name"] for s in document.get("schema", {})}:
        return not_found("Segment not found")

    updated_sequence = await db.sequences.find_one_and_update({"_id": sequence_id}, {
        "$set": data
    })

    if not updated_sequence:
        return not_found()

    document = await db.otus.find_one_and_update({"_id": otu_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.otus.join(db, otu_id, document)

    if await virtool.db.otus.verify(db, otu_id, joined=new) is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate = virtool.otus.find_isolate(old["isolates"], isolate_id)

    await virtool.db.history.add(
        db,
        "edit_sequence",
        old,
        new,
        "Edited sequence {} in {}".format(sequence_id, virtool.otus.format_isolate_name(isolate)),
        req["client"].user_id
    )

    return json_response(virtool.utils.base_processor(updated_sequence))


@routes.delete("/api/otus/{otu_id}/isolates/{isolate_id}/sequences/{sequence_id}")
async def remove_sequence(req):
    """
    Remove a sequence from an isolate.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]
    sequence_id = req.match_info["sequence_id"]

    if not await db.sequences.count({"_id": sequence_id}):
        return not_found()

    old = await virtool.db.otus.join(db, otu_id)

    if not old:
        return not_found()

    isolate = virtool.otus.find_isolate(old["isolates"], isolate_id)

    await db.sequences.delete_one({"_id": sequence_id})

    await db.otus.update_one({"_id": otu_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.otus.join(db, otu_id)

    if await virtool.db.otus.verify(db, otu_id, joined=new) is None:
        await db.otus.update_one({"_id": otu_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.otus.format_isolate_name(isolate)

    await virtool.db.history.add(
        db,
        "remove_sequence",
        old,
        new,
        "Removed sequence {} from {}".format(sequence_id, isolate_name),
        req["client"].user_id
    )

    return no_content()


@routes.get("/api/otus/{otu_id}/history")
async def list_history(req):
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    if not await db.otus.find({"_id": otu_id}).count():
        return not_found()

    documents = await db.history.find({"otu.id": otu_id}).to_list(None)

    return json_response(documents)
