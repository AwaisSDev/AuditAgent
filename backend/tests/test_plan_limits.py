from app.services.plan_limits import agent_limit, event_limit, questionnaire_limit


def test_free_plan_limits():
    assert agent_limit("free") == 1
    assert event_limit("free") == 1_000
    assert questionnaire_limit("free") == 1


def test_starter_plan_limits():
    assert agent_limit("starter") == 5
    assert event_limit("starter") == 50_000
    assert questionnaire_limit("starter") == 5


def test_growth_and_enterprise_are_unlimited():
    for plan in ("growth", "enterprise"):
        assert agent_limit(plan) is None
        assert event_limit(plan) is None
        assert questionnaire_limit(plan) is None


def test_unknown_plan_falls_back_to_free():
    assert agent_limit("nonexistent-plan") == agent_limit("free")
    assert event_limit("nonexistent-plan") == event_limit("free")
    assert questionnaire_limit("nonexistent-plan") == questionnaire_limit("free")
