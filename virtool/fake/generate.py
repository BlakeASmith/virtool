import asyncio
import virtool.startup
from virtool.fake import test_cases, wrapper
from aiojobs import create_scheduler
from contextlib import suppress


async def generate_data_for_test_case(config, test_case, dump_path):
    config["fake"] = True
    app = {
        "config": config,
        "scheduler": await create_scheduler(),
        "fake": wrapper.FakerWrapper()
    }
    await virtool.startup.init_fake_config(app)
    await virtool.startup.init_redis(app)
    await virtool.startup.init_db(app)
    await virtool.startup.init_postgres(app)
    await virtool.startup.init_settings(app)
    await virtool.startup.init_executors(app)

    populate = getattr(test_cases, test_case).populate
    factory = await populate(app)

    await factory.dump(dump_path)

    # Wait for pending tasks to finish.
    pending = asyncio.Task.all_tasks()
    for task in pending:
        if task is not asyncio.tasks.Task.current_task():
            task.cancel()

    with suppress(asyncio.CancelledError):
        await asyncio.gather(*pending)
