import pytest
from app.services.ai_followup import AIFollowUpService
from app.database import ProspectModel, AutomationSettingsModel

def test_ai_fallback_generation():
    settings = AutomationSettingsModel(
        email_signature="Best,\nSam",
        ai_instructions="Keep it friendly."
    )
    prospect = ProspectModel(
        email="john@propertymgmt.com",
        name="John",
        company="Property Management Inc"
    )

    result = AIFollowUpService.generate_follow_up(prospect, settings)

    assert result["subject"].startswith("Re:")
    assert "John" in result["body"]
    assert "Best,\nSam" in result["body"]
    assert len(result["body"].split()) < 150
