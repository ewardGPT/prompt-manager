"""Tests for the PromptsClient SDK."""

from prompt_manager.client import AsyncPromptsClient, PromptsClient


class TestPromptsClient:
    def test_instantiation(self):
        c = PromptsClient()
        assert hasattr(c, "prompts")
        assert hasattr(c, "diff")
        assert hasattr(c, "versions")

    def test_list(self):
        c = PromptsClient()
        prompts = c.prompts.list()
        assert isinstance(prompts, list)

    def test_set_and_get(self):
        c = PromptsClient()
        c.prompts.set("ci_test_prompt", "hello from CI", env="dev")
        result = c.prompts.get("ci_test_prompt", env="dev")
        assert result is not None

    def test_async(self):
        ac = AsyncPromptsClient()
        assert ac.prompts is not None
