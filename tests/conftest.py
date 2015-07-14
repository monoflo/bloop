import bloop
import pytest


def noop(*a, **kw):
    pass


@pytest.fixture
def session():
    class DummyClient:
        pass

    class DummySession:
        def client(self, name):
            assert name == "dynamodb"
            return DummyClient()
    return DummySession()


@pytest.fixture
def engine(session):
    return bloop.Engine(session=session)


@pytest.fixture
def renderer(engine):
    return bloop.condition.ConditionRenderer(engine)


@pytest.fixture
def local_bind(engine):
    engine.client.create_table = noop
    engine.client.validate_table = noop


@pytest.fixture
def UnboundUser(engine):
    class User(engine.model):
        id = bloop.Column(bloop.UUID, hash_key=True)
        age = bloop.Column(bloop.Integer)
        name = bloop.Column(bloop.String)
        email = bloop.Column(bloop.String)
        joined = bloop.Column(bloop.DateTime)

        by_email = bloop.GlobalSecondaryIndex(hash_key='email',
                                              projection='all')
    return User


@pytest.fixture
def User(UnboundUser, engine, local_bind):
    engine.bind()
    return UnboundUser