import pytest

from fpa import etl
from fpa.generate import generate


@pytest.fixture(scope="session")
def raw(tmp_path_factory):
    path = tmp_path_factory.mktemp("raw")
    generate(seed=7, out=path)
    return path


@pytest.fixture(scope="session")
def close(raw):
    return etl.run(raw)
