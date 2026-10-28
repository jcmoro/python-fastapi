from uuid import uuid4

import pytest
from pydantic import ValidationError

from contexts.assistant.ui.schemas import RecommendationResponse


class TestRecommendationInvariant:
    def test_b14_chosen_with_every_field_is_valid(self) -> None:
        response = RecommendationResponse(
            product_id=uuid4(), sku="BOOT-1", score=0.67, reason="chosen"
        )

        assert response.reason == "chosen"

    @pytest.mark.parametrize("reason", ["below_threshold", "no_assessments"])
    def test_b14_no_choice_with_every_field_null_is_valid(self, reason: str) -> None:
        response = RecommendationResponse(product_id=None, sku=None, score=None, reason=reason)

        assert response.product_id is None

    @pytest.mark.parametrize(
        "missing", [{"product_id": None}, {"sku": None}, {"score": None}]
    )
    def test_b14_chosen_requires_every_field(self, missing: dict[str, None]) -> None:
        fields: dict[str, object] = {
            "product_id": uuid4(),
            "sku": "BOOT-1",
            "score": 1.0,
            "reason": "chosen",
        }
        fields.update(missing)

        with pytest.raises(ValidationError, match="chosen"):
            RecommendationResponse.model_validate(fields)

    def test_b14_no_choice_must_not_carry_a_product(self) -> None:
        with pytest.raises(ValidationError, match="chosen"):
            RecommendationResponse(
                product_id=uuid4(), sku=None, score=None, reason="below_threshold"
            )

    def test_reason_is_a_closed_code(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationResponse(product_id=None, sku=None, score=None, reason="max_steps")
