import os
import pytest

from virtool.permissions import PERMISSIONS

from .mock_mongo import MockMongo
from .mock_socket import MockSocket
from .mock_settings import MockSettings
from .mock_connection import MockConnection
from .mock_transaction import MockTransaction


@pytest.fixture
def socket():
    return lambda settings: MockSocket(settings)


@pytest.fixture
def blind_socket(called_tester):
    return MockConnection({
        "add_connection": called_tester(),
        "remove_connection": called_tester(),
        "handle_message": called_tester()
    })


@pytest.fixture(scope="session")
def settings():
    return MockSettings()


@pytest.fixture
def mock_connection(user):
    def create(name="test", permissions=None, administrator=False, authorized=True):
        bound_user = user(name, permissions, administrator)
        return MockConnection(bound_user, authorized)

    return create


@pytest.fixture(scope="session")
def mock_mongo():
    mock = MockMongo()
    yield mock
    mock.delete()


@pytest.fixture
def mock_transaction(mock_connection):
    def create(message, username="test", permissions=None, administrator=False, authorized=True):
        connection = mock_connection(username, permissions, administrator, authorized)
        return MockTransaction(message, connection)

    return create


@pytest.fixture(scope="session")
def static_time():
    from datetime import datetime
    return datetime(2000, 1, 1)


@pytest.fixture(scope="session")
def data_dir(tmpdir_factory):
    # Set up a mock data directory.
    mock_dir = tmpdir_factory.mktemp("data")

    for path in ["download", "hmm", "logs", "reference", "samples", "upload"]:
        os.mkdir(os.path.join(str(mock_dir), path))

    return mock_dir


@pytest.fixture(scope="session")
def called_tester():

    class Func:

        def __init__(self):
            self.was_called = False
            self.with_args = None
            self.with_kwargs = None

        def __call__(self, *args, **kwargs):
            self.was_called = True
            self.with_args = args
            self.with_kwargs = kwargs

    def create():
        return Func()

    return create


@pytest.fixture(scope="function")
def temp_mongo(session_mongo, io_loop):
    import motor

    yield motor.MotorClient(io_loop=io_loop)[session_mongo.name]

    session_mongo.clean()


@pytest.fixture(scope="session")
def user():
    def create(name="test", permissions=None, administrator=False):
        if isinstance(permissions, list):
            pass
        elif permissions == "all" or administrator:
            permissions = list(PERMISSIONS)
        else:
            permissions = list()

        permissions = {key: key in permissions for key in PERMISSIONS}

        groups = list()

        if administrator:
            groups.append("administrator")

        return {
            "name": name,
            "permissions": permissions,
            "groups": groups
        }

    return create
