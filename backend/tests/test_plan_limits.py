from app.services.plan_limits import agent_limit, event_limit, questionnaire_limit


def test_free_plan_limits():
    assert agent_limit("free") == 1
    assert event_limit("free") == 2_500
    assert questionnaire_limit("free") == 1


def test_starter_plan_limits():
    assert agent_limit("starter") == 10
    assert event_limit("starter") == 50_000
    assert questionnaire_limit("starter") == 10


def test_pro_plan_limits():
    assert agent_limit("pro") == 50
    assert event_limit("pro") == 250_000
    assert questionnaire_limit("pro") is None


def test_enterprise_is_unlimited():
    assert agent_limit("enterprise") is None
    assert event_limit("enterprise") is None
    assert questionnaire_limit("enterprise") is None


def test_unknown_plan_falls_back_to_free():
    assert agent_limit("nonexistent-plan") == agent_limit("free")
    assert event_limit("nonexistent-plan") == event_limit("free")
    assert questionnaire_limit("nonexistent-plan") == questionnaire_limit("free")
