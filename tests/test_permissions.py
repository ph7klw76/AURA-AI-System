from core.permissions import requires_human_approval, is_action_allowed


def test_send_email_requires_approval():
    needs, reason = requires_human_approval("send email to my collaborator about the results")
    assert needs is True
    assert reason


def test_summarize_does_not_require_approval():
    needs, _ = requires_human_approval("summarise this research idea for me")
    assert needs is False


def test_modify_profile_requires_approval():
    needs, _ = requires_human_approval("modify research_profile.yaml to add new topics")
    assert needs is True


def test_contact_author_requires_approval():
    needs, _ = requires_human_approval("contact author of this paper")
    assert needs is True


def test_search_papers_allowed():
    assert is_action_allowed("search_papers") is True


def test_send_email_not_allowed():
    assert is_action_allowed("send_email") is False


def test_submit_grant_not_allowed():
    assert is_action_allowed("submit_grant") is False
