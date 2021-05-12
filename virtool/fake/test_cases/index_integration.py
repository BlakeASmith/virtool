from virtool.fake.factory import TestCaseDataFactory
from virtool.fake.identifiers import USER_ID


async def populate(app):
    factory = TestCaseDataFactory(app, USER_ID, "index_integration_test_job")

    reference = await factory.reference()
    index_final = await factory.index(ref_id=reference["_id"], finalize=True)

    name = "index_integration_text"

    analysis = await factory.analysis(
            index_id=index_final["_id"],
            ref_id=reference["_id"],
            workflow=name,
    )

    await factory.job(workflow=name, args={
        "index_id": index_final["_id"],
        "analysis_id": analysis["_id"],
    })
