"""
Provides request handlers for file downloads.

"""
import gzip
import json
from aiohttp import web

import virtool.bio
import virtool.db.downloads
import virtool.db.history
import virtool.db.otus
import virtool.db.references
import virtool.errors
import virtool.http.routes
import virtool.otus
from virtool.api.utils import CustomEncoder, not_found

routes = virtool.http.routes.Routes()


@routes.get("/download/otus/{otu_id}/isolates/{isolate_id}")
async def download_isolate(req):
    """
    Download a FASTA file containing the sequences for a single Virtool isolate.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]
    isolate_id = req.match_info["isolate_id"]

    try:
        filename, fasta = await virtool.db.downloads.generate_isolate_fasta(db, otu_id, isolate_id)
    except virtool.errors.DatabaseError as err:
        if "OTU does not exist" in str(err):
            return not_found("OTU does not exist")

        if "Isolate does not exist" in str(err):
            return not_found("Isolate does not exist")

        raise

    return web.Response(text=fasta, headers={
        "Content-Disposition": "attachment; filename='{}'".format(filename)
    })


@routes.get("/download/otus/{otu_id}")
async def download_otu(req):
    """
    Download a FASTA file containing the sequences for all isolates in a single Virtool otu.

    """
    db = req.app["db"]

    otu_id = req.match_info["otu_id"]

    try:
        filename, fasta = await virtool.db.downloads.generate_otu_fasta(db, otu_id)
    except virtool.errors.DatabaseError as err:
        if "Sequence does not exist" in str(err):
            return not_found("Sequence does not exist")

        if "OTU does not exist" in str(err):
            return not_found("OTU does not exist")

        raise

    if not fasta:
        return web.Response(status=404)

    return web.Response(text=fasta, headers={
        "Content-Disposition": "attachment; filename='{}'".format(filename)
    })


@routes.get("/download/refs/{ref_id}")
async def download_reference(req):
    """
    Export all otus and sequences for a given reference as a gzipped JSON string. Made available as a downloadable file
    named ``reference.json.gz``.

    """
    db = req.app["db"]

    ref_id = req.match_info["ref_id"]

    document = await db.references.find_one(ref_id, ["data_type", "organism"])

    if document is None:
        return not_found()

    scope = req.query.get("scope", "built")

    if scope not in ["built", "unbuilt", "unverified"]:
        scope = "built"

    otu_list = await virtool.db.references.export(db, ref_id, scope)

    data = {
        "data": otu_list,
        "data_type": document["data_type"],
        "organism": document["organism"]
    }

    # Convert the list of viruses to a JSON-formatted string.
    json_string = json.dumps(data, cls=CustomEncoder)

    # Compress the JSON string with gzip.
    body = await req.app["run_in_process"](gzip.compress, bytes(json_string, "utf-8"))

    return web.Response(
        headers={"Content-Disposition": "attachment; filename='reference.{}.json.gz'".format(scope)},
        content_type="application/gzip",
        body=body
    )


@routes.get("/download/sequences/{sequence_id}")
async def download_sequence(req):
    """
    Download a FASTA file containing a single Virtool sequence.

    """
    db = req.app["db"]

    sequence_id = req.match_info["sequence_id"]

    try:
        filename, fasta = await virtool.db.downloads.generate_sequence_fasta(db, sequence_id)
    except virtool.errors.DatabaseError as err:
        if "Sequence does not exist" in str(err):
            return not_found("Sequence does not exist")

        if "Isolate does not exist" in str(err):
            return not_found("Isolate does not exist")

        if "OTU does not exist" in str(err):
            return not_found("OTU does not exist")

        raise

    if fasta is None:
        return web.Response(status=404)

    return web.Response(text=fasta, headers={
        "Content-Disposition": "attachment; filename='{}'".format(filename)
    })
