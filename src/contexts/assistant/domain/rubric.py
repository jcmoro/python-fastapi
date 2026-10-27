from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RubricQuestion:
    id: str
    instructions: str
    yes_means: str
    no_means: str


MEETS_REQUIREMENTS = RubricQuestion(
    id="meets_requirements",
    instructions="Does the product meet the explicit requirements stated in the question?",
    yes_means=(
        "The product satisfies every requirement the question states explicitly. "
        "If the question states no explicit requirements, answer yes."
    ),
    no_means="The product fails at least one requirement the question states explicitly.",
)

SUITABLE_FOR_USE = RubricQuestion(
    id="suitable_for_use",
    instructions="Is the product suitable for the use the question asks about?",
    yes_means="The product is a good fit for that use.",
    no_means="The product is not a good fit for that use.",
)

RUBRIC = (MEETS_REQUIREMENTS, SUITABLE_FOR_USE)
