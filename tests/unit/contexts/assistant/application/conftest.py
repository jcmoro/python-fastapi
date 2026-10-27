import pytest
from tests.fakes.llm_client import FakeLLMClient


@pytest.fixture
def llm_client() -> FakeLLMClient:
    return FakeLLMClient()
