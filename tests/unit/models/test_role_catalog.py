import pytest
from pydantic import ValidationError

from app.models.role_catalog import CompanyRoleWriteRequest


def test_company_role_request_normalizes_role_and_nested_content():
    request = CompanyRoleWriteRequest.model_validate(
        {
            "name": "  Senior   Data Scientist ",
            "summary": "  Leads applied analytics.  ",
            "responsibilities": [{"statement": "  Lead   model reviews. "}],
            "goals": [{"title": "  Improve model quality  ", "description": " "}],
            "competencies": [
                {
                    "name": " Machine   learning ",
                    "expected_level": " Expert ",
                    "description": None,
                }
            ],
        }
    )

    assert request.name == "Senior Data Scientist"
    assert request.summary == "Leads applied analytics."
    assert request.responsibilities[0].statement == "Lead model reviews."
    assert request.goals[0].title == "Improve model quality"
    assert request.goals[0].description is None
    assert request.competencies[0].name == "Machine learning"
    assert request.competencies[0].expected_level == "Expert"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "  "},
        {"name": "Engineer", "unexpected": True},
        {
            "name": "Engineer",
            "responsibilities": [{"statement": "  "}],
        },
        {"name": "Engineer", "goals": [{"title": "  "}]},
        {"name": "Engineer", "competencies": [{"name": "  "}]},
    ],
)
def test_company_role_request_rejects_invalid_entries(payload):
    with pytest.raises(ValidationError):
        CompanyRoleWriteRequest.model_validate(payload)
