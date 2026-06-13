"""PII scrubber tests — scrub-at-ingest invariant."""

from aprntc.trajectory import (
    Collector,
    ContentPart,
    ContentType,
    Episode,
    Label,
    LabelSource,
    PiiStatus,
    Step,
    StepType,
    Turn,
    scrub_episode,
    scrub_text,
)


def test_scrub_text_email_phone_card_ssn():
    s = "mail me at john.doe@example.com or call +1 415 555 1234"
    out = scrub_text(s)
    assert "john.doe@example.com" not in out
    assert "[EMAIL]" in out and "[PHONE]" in out


def test_scrub_text_ssn_and_card():
    assert "[SSN]" in scrub_text("ssn 123-45-6789")
    assert "[CARD]" in scrub_text("card 4111 1111 1111 1111")


def test_scrub_text_secret_token():
    assert "[SECRET]" in scrub_text("token sk-ABCDEF0123456789XY")


def test_scrub_text_none_passthrough():
    assert scrub_text(None) is None
    assert scrub_text("") == ""


def test_scrub_is_idempotent():
    once = scrub_text("email a@b.com")
    assert scrub_text(once) == once


def test_scrub_episode_covers_all_freetext_and_sets_status():
    e = Episode(
        task_input="user a@b.com needs help",
        collector=Collector.SDK_WRAPPER,
        final_output="contact me at c@d.com",
        input_context=["prior: e@f.com"],
        turns=[
            Turn(
                turn_index=0,
                user_content=[ContentPart.text_part("my email is g@h.com")],
                agent_content=[ContentPart.text_part("ok")],
                reasoning_content="the user g@h.com wants...",
                steps=[
                    Step(step_index=0, type=StepType.TOOL_CALL, tool_name="lookup",
                         tool_args={"email": "i@j.com"},
                         tool_result={"note": "ssn 123-45-6789"}),
                ],
            )
        ],
        labels=[Label(source=LabelSource.HUMAN, score=0.5, rationale="bad: leaked k@l.com")],
    )
    s = scrub_episode(e)
    blob = str(s.to_dict())
    # No raw emails / ssn remain anywhere
    for raw in ("a@b.com", "c@d.com", "e@f.com", "g@h.com", "i@j.com", "k@l.com", "123-45-6789"):
        assert raw not in blob
    assert s.pii_status is PiiStatus.SCRUBBED
    # nested tool_args/result + reasoning + label rationale scrubbed
    assert "[EMAIL]" in s.turns[0].steps[0].tool_args["email"]
    assert "[SSN]" in s.turns[0].steps[0].tool_result["note"]
    assert "[EMAIL]" in (s.turns[0].reasoning_content or "")
    assert "[EMAIL]" in (s.labels[0].rationale or "")


def test_scrub_does_not_mutate_original():
    e = Episode(task_input="a@b.com", collector=Collector.SDK_WRAPPER)
    scrub_episode(e)
    assert e.pii_status is PiiStatus.RAW
    assert "a@b.com" in e.task_input
