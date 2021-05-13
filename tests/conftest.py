from pathlib import Path

pytest_plugins = [
    "tests.fixtures.client",
    "tests.fixtures.core",
    "tests.fixtures.db",
    "tests.fixtures.dispatcher",
    "tests.fixtures.documents",
    "tests.fixtures.fake",
    "tests.fixtures.groups",
    "tests.fixtures.history",
    "tests.fixtures.indexes",
    "tests.fixtures.jobs",
    "tests.fixtures.postgres",
    "tests.fixtures.redis",
    "tests.fixtures.references",
    "tests.fixtures.response",
    "tests.fixtures.setup",
    "tests.fixtures.users",
    "tests.fixtures.otus",
    "tests.fixtures.uploads",
    "tests.fixtures.labels",
    "tests.fixtures.tasks",
    "tests.fixtures.settings",
    "tests.fixtures.subtractions",
]


TESTS_PATH = Path(__file__).parent
TEST_FILES_PATH = Path(__file__).parent/"test_files"


def pytest_addoption(parser):
    parser.addoption(
        "--db-connection-string",
        action="store",
        default="mongodb://localhost:27017"
    )

    parser.addoption(
        "--redis-connection-string",
        action="store",
        default="redis://localhost:6379"
    )

    parser.addoption(
        "--postgres-connection-string",
        action="store",
        default="postgresql+asyncpg://virtool:virtool@localhost"
    )
