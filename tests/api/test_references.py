import pytest
from aiohttp.test_utils import make_mocked_coro


async def test_get_release(mocker, spawn_client, id_exists, resp_is):
    client = await spawn_client(authorize=True)

    m_fetch_and_update_release = mocker.patch(
        "virtool.db.references.fetch_and_update_release",
        make_mocked_coro({
            "_id": "release"
        })
    )

    resp = await client.get("/api/refs/foo/release")

    id_exists.assert_called_with(
        client.db.references,
        "foo"
    )

    if not id_exists:
        assert await resp_is.not_found(resp)
        return

    assert resp.status == 200

    assert await resp.json() == {
        "_id": "release"
    }

    m_fetch_and_update_release.assert_called_with(
        client.app,
        "foo"
    )


@pytest.mark.parametrize("empty", [True, False])
async def test_list_updates(empty, mocker, spawn_client, id_exists, resp_is):
    client = await spawn_client(authorize=True)

    m_get_one_field = mocker.patch(
        "virtool.db.utils.get_one_field",
        make_mocked_coro(None if empty else [
            "a",
            "b",
            "c"
        ])
    )

    resp = await client.get("/api/refs/foo/updates")

    id_exists.assert_called_with(
        client.db.references,
        "foo"
    )

    if not id_exists:
        assert await resp_is.not_found(resp)
        return

    assert resp.status == 200
    assert await resp.json() == [] if None else [
        "c",
        "b",
        "a"
    ]

    m_get_one_field.assert_called_with(
        client.db.references,
        "updates",
        "foo"
    )


@pytest.mark.parametrize("release_id", ["bar", None])
async def test_update(release_id, mocker, spawn_client, check_ref_right, id_exists, resp_is):
    client = await spawn_client(authorize=True)

    m_finish_update = mocker.patch("virtool.db.references.finish_update", make_mocked_coro())

    m_register = mocker.patch(
        "virtool.db.processes.register",
        make_mocked_coro({
            "id": "process"
        })
    )

    m_update = mocker.patch(
        "virtool.db.references.update",
        make_mocked_coro((
            {
                "id": "bar"
            },
            {
                "id": "update",
                "created_at": "time"
            }
        ))
    )

    if release_id:
        resp = await client.post("/api/refs/foo/updates", {
            "release_id": release_id
        })
    else:
        resp = await client.post("/api/refs/foo/updates")

    id_exists.assert_called_with(
        client.db.references,
        "foo"
    )

    if not id_exists:
        assert await resp_is.not_found(resp)
        return

    if not check_ref_right:
        assert await resp_is.insufficient_rights(resp)
        return

    m_register.assert_called_with(
        client.db,
        "update_remote_reference"
    )

    m_update.assert_called_with(
        client.app,
        "process",
        "foo",
        release_id,
        "test"
    )

    m_finish_update.assert_called_with(
        client.app,
        "foo",
        "time",
        "process",
        {
            "id": "bar"
        },
        "test"
    )

    assert resp.status == 201

    assert await resp.json() == {
        "id": "update",
        "created_at": "time"
    }


async def test_find_indexes(mocker, spawn_client, id_exists, md_proxy, resp_is):
    client = await spawn_client(authorize=True)

    body = {
        "documents": ["a", "b", "c"]
    }

    m_find = mocker.patch("virtool.db.indexes.find", make_mocked_coro(body))

    resp = await client.get("/api/refs/foo/indexes")

    if not id_exists:
        assert await resp_is.not_found(resp)
        return

    assert resp.status == 200

    assert await resp.json() == body

    m_find.assert_called_with(
        client.db,
        md_proxy(),
        ref_id="foo"
    )


async def test_create(mocker, spawn_client, test_random_alphanumeric, static_time):
    client = await spawn_client(authorize=True, permissions=["create_ref"])

    default_source_type = [
        "strain",
        "isolate"
    ]

    client.app["settings"] = {
        "default_source_types": default_source_type
    }

    data = {
        "name": "Test Viruses",
        "description": "A bunch of viruses used for testing",
        "data_type": "genome",
        "organism": "virus"
    }

    m_get_otu_count = mocker.patch("virtool.db.references.get_otu_count", make_mocked_coro(22))
    m_get_unbuilt_count = mocker.patch("virtool.db.references.get_unbuilt_count", make_mocked_coro(5))

    resp = await client.post("/api/refs", data)

    assert resp.status == 201

    assert resp.headers["Location"] == "/api/refs/" + test_random_alphanumeric.history[0]

    assert await resp.json() == dict(
        data,
        id=test_random_alphanumeric.history[0],
        created_at="2015-10-06T20:00:00Z",
        user={
            "id": "test"
        },
        users=[{
            "build": True,
            "id": "test",
            "modify": True,
            "modify_otu": True,
            "remove": True
        }],
        groups=[],
        contributors=[],
        internal_control=None,
        restrict_source_types=False,
        otu_count=22,
        unbuilt_change_count=5,
        source_types=default_source_type,
        latest_build=None
    )

    m_get_otu_count.assert_called_with(
        client.db,
        test_random_alphanumeric.history[0]
    )

    m_get_unbuilt_count.assert_called_with(
        client.db,
        test_random_alphanumeric.history[0]
    )


@pytest.mark.parametrize("control_exists", [True, False])
@pytest.mark.parametrize("control_id", [None, "", "baz"])
async def test_edit(control_exists, control_id, mocker, spawn_client, check_ref_right, id_exists, resp_is):
    client = await spawn_client(authorize=True)

    m_find_one_and_update = mocker.patch.object(
        client.db.references,
        "find_one_and_update",
        make_mocked_coro({
            "_id": "foo",
            "name": "Test Reference"
        })
    )

    m_get_computed = mocker.patch(
        "virtool.db.references.get_computed",
        make_mocked_coro({
            "computed": True
        })
    )

    m_get_internal_control = mocker.patch(
        "virtool.db.references.get_internal_control",
        make_mocked_coro({"id": "baz"} if control_exists else None)
    )

    data = {
        "name": "Tester",
        "description": "This is a test reference."
    }

    if control_id is not None:
        data["internal_control"] = control_id

    resp = await client.patch("/api/refs/foo", data)

    id_exists.assert_called_with(
        client.db.references,
        "foo"
    )

    if not id_exists:
        assert await resp_is.not_found(resp)
        return

    check_ref_right.assert_called_with(
        mocker.ANY,
        "foo",
        "modify"
    )

    assert check_ref_right.called_with_req()

    if not check_ref_right:
        assert await resp_is.insufficient_rights(resp)
        return


@pytest.mark.parametrize("error", [None, "400_dne", "400_exists", "404"])
@pytest.mark.parametrize("field", ["group", "user"])
async def test_add_group_or_user(error, field, spawn_client, check_ref_right, resp_is, static_time):
    """
    Test that the group or user is added to the reference when no error condition exists.

    Test for the following error conditions:
    - 404: ref does not exist
    - 400_exists: group or user already exists in ref
    - 400_dne: group or user does not exist

    """
    client = await spawn_client(authorize=True)

    document = {
        "_id": "foo",
        "groups": [],
        "users": []
    }

    # Add group and user subdocuments to make sure a 400 is returned complaining about the user or group already
    # existing in the ref.
    if error == "400_exists":
        document["groups"].append({
            "id": "tech"
        })

        document["users"].append({
            "id": "fred"
        })

    # Add group and user document to their collections unless we want to trigger a 400 complaining about the user or
    # group already not existing.
    if error != "400_dne":
        await client.db.groups.insert_one({
            "_id": "tech"
        })

        await client.db.users.insert_one({
            "_id": "fred"
        })

    # Don't insert the ref document if we want to trigger a 404.
    if error != "404":
        await client.db.references.insert_one(document)

    url = "/api/refs/foo/{}s".format(field)

    resp = await client.post(url, {
        field + "_id": "tech" if field == "group" else "fred",
        "modify": True
    })

    if error == "404":
        assert await resp_is.not_found(resp)
        return

    if not check_ref_right:
        assert await resp_is.insufficient_rights(resp)
        return

    if error == "400_dne":
        assert await resp_is.bad_request(resp, "{} does not exist".format(field.capitalize()))
        return

    if error == "400_exists":
        assert await resp_is.bad_request(resp, "{} already exists".format(field.capitalize()))
        return

    assert resp.status == 201

    assert await resp.json() == {
        "id": "tech" if field == "group" else "fred",
        "created_at": static_time.iso,
        "build": False,
        "modify": True,
        "modify_otu": False,
        "remove": False
    }


@pytest.mark.parametrize("error", [None, "404_field", "404_ref"])
@pytest.mark.parametrize("field", ["group", "user"])
async def test_edit_group_or_user(error, field, spawn_client, check_ref_right, resp_is):
    client = await spawn_client(authorize=True)

    document = {
        "_id": "foo",
        "groups": [],
        "users": []
    }

    if error != "404_field":
        document["groups"].append({
            "id": "tech",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": False
        })

        document["users"].append({
            "id": "fred",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": False
        })

    if error != "404_ref":
        await client.db.references.insert_one(document)

    subdocument_id = "tech" if field == "group" else "fred"

    url = "/api/refs/foo/{}s/{}".format(field, subdocument_id)

    resp = await client.patch(url, {
        "remove": True
    })

    if error:
        assert await resp_is.not_found(resp)
        return

    if not check_ref_right:
        assert await resp_is.insufficient_rights(resp)
        return

    assert resp.status == 200

    assert await resp.json() == {
        "id": subdocument_id,
        "build": False,
        "modify": False,
        "modify_otu": False,
        "remove": True
    }

    assert await client.db.references.find_one() == {
        "_id": "foo",
        "groups": [{
            "id": "tech",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": field == "group"
        }],
        "users": [{
            "id": "fred",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": field == "user"
        }]
    }


@pytest.mark.parametrize("error", [None, "404_field", "404_ref"])
@pytest.mark.parametrize("field", ["group", "user"])
async def test_delete_group_or_user(error, field, spawn_client, check_ref_right, resp_is):
    client = await spawn_client(authorize=True)

    document = {
        "_id": "foo",
        "groups": [],
        "users": []
    }

    if error != "404_field":
        document["groups"].append({
            "id": "tech",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": False
        })

        document["users"].append({
            "id": "fred",
            "build": False,
            "modify": False,
            "modify_otu": False,
            "remove": False
        })

    if error != "404_ref":
        await client.db.references.insert_one(document)

    subdocument_id = "tech" if field == "group" else "fred"

    url = "/api/refs/foo/{}s/{}".format(field, subdocument_id)

    resp = await client.delete(url)

    if error:
        assert await resp_is.not_found(resp)
        return

    if not check_ref_right:
        assert await resp_is.insufficient_rights(resp)
        return

    assert resp.status == 204

    if field == "group":
        expected = {
            **document,
            "groups": []
        }
    else:
        expected = {
            **document,
            "users": []
        }

    assert await client.db.references.find_one() == expected
