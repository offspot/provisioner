import pytest

from provisioner.context import Context

Context.setup()

@pytest.fixture
def context():
    yield True
