"""Day 3 edge cases — the ways this breaks in front of someone.

Read tests/conftest.py first for the offline/live split. Everything here runs
offline except the four cases at the bottom, which are marked `live`.

Each test says what it is defending against, because a test whose purpose you
cannot reconstruct in six months is a test you will delete when it goes red.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.aiact.classify import (
    MAX_DESCRIPTION_CHARS,
    SYSTEM_BLOCKS,
    DescriptionTooLongError,
    classify,
    classify_with_meta,
    validate_description,
)
from src.aiact.obligations import obligations_for
from src.aiact.schema import (
    AnnexIIIDerogation,
    Art25Trigger,
    Classification,
    ModelVerdict,
    RiskTier,
    Role,
)
from toolkit.costlog import UnknownModelError, price, summarise
from toolkit.structured import RefusalError, SchemaRetryError, cached_system

from conftest import FakeClient, FakeMessage, text_block, usage


# --- 1. Input that must never reach the API ---------------------------------
# The cheapest failure is the one that never opens a socket. Each of these
# would otherwise be a paid call that could not produce anything useful.


@pytest.mark.parametrize("text", ["", "   ", "\n\t  \n", None])
def test_empty_input_is_refused_without_calling_the_api(text):
    with pytest.raises(ValueError, match="empty"):
        validate_description(text)


def test_overlong_input_is_refused_and_says_by_how_much():
    too_long = "x" * (MAX_DESCRIPTION_CHARS + 1)
    with pytest.raises(DescriptionTooLongError) as exc:
        validate_description(too_long)
    # The message must carry both numbers: "too long" without a limit is a
    # dead end for whoever pasted it.
    assert str(MAX_DESCRIPTION_CHARS) in str(exc.value).replace(",", "")
    assert exc.value.length == MAX_DESCRIPTION_CHARS + 1


def test_input_at_exactly_the_limit_is_allowed():
    # Off-by-one guard: the limit is inclusive, and a boundary that quietly
    # moves is how a valid description starts getting refused.
    assert len(validate_description("x" * MAX_DESCRIPTION_CHARS)) == MAX_DESCRIPTION_CHARS


def test_classify_rejects_empty_before_constructing_a_client():
    # No client is passed, so if this ever reached call_schema it would try to
    # build a real Anthropic() and fail on a missing key — a different error.
    # Matching on "empty" is what makes this test meaningful.
    with pytest.raises(ValueError, match="empty"):
        classify("   ")


def test_whitespace_is_stripped_not_just_checked():
    assert validate_description("  NavGuard flags NAV anomalies.  ") == (
        "NavGuard flags NAV anomalies."
    )


# --- 2. The two documented ways structured output breaks --------------------
# Both are checked before the payload is read, because a truncated or refused
# response can still carry something that looks parseable.


def test_truncation_at_max_tokens_retries_with_a_bigger_ceiling(verdict_dict):
    """The classic structured-output failure: JSON cut off mid-object.

    Retrying with the SAME ceiling truncates again, so the wrapper must double
    it. This asserts on the second call's max_tokens, not just on success —
    a retry that succeeds by luck would otherwise pass.

    The truncated reply carries the half-object the model actually sent, and
    that matters: the 2026-09-15 review found the wrapper calling the SDK's
    messages.parse(), which validates the text BEFORE returning, so a real
    truncated reply raised inside the SDK and this branch was unreachable in
    production. The fake's parse() now does the same, and this test fails
    against that commit.
    """
    good = ModelVerdict.model_validate(verdict_dict)
    cut_off = good.model_dump_json()[:40]  # mid-object, as max_tokens leaves it
    client = FakeClient(
        FakeMessage(stop_reason="max_tokens", content=[text_block(cut_off)]),
        FakeMessage(stop_reason="end_turn", content=[text_block(good.model_dump_json())]),
    )

    record, result = classify_with_meta("A vendor description.", client=client)

    assert result.attempts == 2
    assert isinstance(record, Classification)
    first, second = client.calls[0]["max_tokens"], client.calls[1]["max_tokens"]
    assert second == first * 2, "a truncated response must be retried with more room"


def test_the_fake_client_fails_a_truncated_parse_the_way_the_sdk_does(verdict_dict):
    """Guards the guard. If the fake's parse() stopped validating, the test
    above could go green again with the production bug back in place."""
    from pydantic import ValidationError

    good = ModelVerdict.model_validate(verdict_dict)
    client = FakeClient(
        FakeMessage(stop_reason="max_tokens", content=[text_block(good.model_dump_json()[:40])])
    )
    with pytest.raises(ValidationError):
        client.messages.parse(model="x", max_tokens=1, messages=[], output_format=ModelVerdict)


def test_the_real_sdk_hands_back_a_truncated_reply_raw(verdict_dict):
    """The one test that crosses the SDK boundary, with the network mocked.

    A real `anthropic.Anthropic` client, a real request through the SDK's
    own serialisation, and a canned HTTP reply — so this proves what the fake
    cannot: that `output_config` is accepted by messages.create() as we build
    it, and that a truncated reply comes back as a Message with
    stop_reason == "max_tokens" instead of an exception. No key, no network,
    no money.

    `httpx2` is the SDK's vendored copy of httpx (anthropic 1.x); the client
    refuses a plain `httpx.Client`, and the mock transport must come from the
    same package.
    """
    import httpx2 as httpx
    from anthropic import Anthropic

    good = ModelVerdict.model_validate(verdict_dict)
    replies = iter(
        [
            ("max_tokens", good.model_dump_json()[:40]),
            ("end_turn", good.model_dump_json()),
        ]
    )
    bodies_sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies_sent.append(json.loads(request.content))
        stop_reason, text = next(replies)
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [{"type": "text", "text": text}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 9_000, "output_tokens": 100},
            },
        )

    client = Anthropic(
        api_key="not-a-real-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )

    record, result = classify_with_meta("A vendor description.", client=client)

    assert isinstance(record, Classification)
    assert result.attempts == 2
    assert result.usage.input_tokens == 18_000, "both replies were billed"
    fmt = bodies_sent[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and "properties" in fmt["schema"]
    assert bodies_sent[1]["max_tokens"] == bodies_sent[0]["max_tokens"] * 2


# --- 2b. Every reply is billed, including the ones that failed ---------------
# Before 2026-09-15, result.usage was the final attempt's usage alone and the
# adapters recorded spend only after a success. A classification that
# truncated at 9,000 tokens and then succeeded at 10 was priced at 10; a
# refusal or an exhausted retry was priced at nothing. The demo's spend cap
# could be walked around by sending requests that fail.


def test_usage_is_summed_over_every_attempt(verdict_dict):
    good = ModelVerdict.model_validate(verdict_dict)
    client = FakeClient(
        FakeMessage(
            stop_reason="max_tokens",
            content=[text_block("{")],
            usage=usage(input_tokens=9_000, output_tokens=2_048),
        ),
        FakeMessage(
            stop_reason="end_turn",
            content=[text_block(good.model_dump_json())],
            usage=usage(input_tokens=10, output_tokens=300),
        ),
    )

    _, result = classify_with_meta("A vendor description.", client=client)

    assert result.usage.input_tokens == 9_010
    assert result.usage.output_tokens == 2_348
    assert result.usage.responses == 2


def test_a_refusal_carries_the_usage_of_the_call_that_refused():
    client = FakeClient(FakeMessage(stop_reason="refusal", usage=usage(input_tokens=7_000)))
    with pytest.raises(RefusalError) as exc:
        classify("A vendor description.", client=client)
    assert exc.value.usage.input_tokens == 7_000
    assert exc.value.model  # the adapter needs it to price the usage


def test_exhausted_retries_carry_the_usage_of_every_attempt():
    junk = text_block("{not json")
    client = FakeClient(
        *[FakeMessage(stop_reason="end_turn", content=[junk], usage=usage(input_tokens=1_000))] * 3
    )
    with pytest.raises(SchemaRetryError) as exc:
        classify("A vendor description.", client=client, max_attempts=3)
    assert exc.value.usage.input_tokens == 3_000
    assert exc.value.usage.responses == 3


def test_the_api_charges_the_cap_for_a_classification_that_failed(monkeypatch):
    """The failure path, not the success path, is where the cap was porous."""
    from fastapi.testclient import TestClient

    import toolkit.costlog as costlog
    import webapp.main as main
    from toolkit.structured import Usage

    def fail(description, **kwargs):
        spent = Usage()
        spent.add(usage(input_tokens=1_000_000, output_tokens=0))  # $1 on Haiku
        raise SchemaRetryError(3, "field required", usage=spent, model="claude-haiku-4-5")

    monkeypatch.setattr(main, "classify_with_meta", fail)
    costlog.reset_spend()
    try:
        response = TestClient(main.app).post("/classify", json={"description": "A vendor tool."})
        assert response.status_code == 502
        assert costlog.spent_usd() == pytest.approx(1.0)
    finally:
        costlog.reset_spend()


def test_a_refusal_is_not_retried():
    """A refusal is a decision about the content, not a formatting slip.

    Asking again in the same words spends money to receive the same answer.
    The FakeClient is scripted with ONE response, so a retry would raise
    "ran out of scripted responses" and this test would fail loudly.
    """
    client = FakeClient(FakeMessage(stop_reason="refusal"))
    with pytest.raises(RefusalError):
        classify("A vendor description.", client=client)
    assert len(client.calls) == 1


def test_unparseable_output_retries_with_the_exact_error_then_gives_up():
    """A blind retry re-rolls the dice; a retry that quotes the error usually works.

    Here every attempt fails, so the assertion is on the two things that must
    be true of the failure: it raises rather than returning a half-filled
    object, and the retry actually fed the validation error back.
    """
    junk = text_block("{not json")
    client = FakeClient(*[FakeMessage(stop_reason="end_turn", content=[junk])] * 3)

    with pytest.raises(SchemaRetryError) as exc:
        classify("A vendor description.", client=client, max_attempts=3)

    assert exc.value.attempts == 3
    assert len(client.calls) == 3
    follow_up = client.calls[1]["messages"][-1]["content"]
    assert "did not match the required schema" in follow_up
    assert "Change only what the error names" in follow_up


def test_no_partial_record_is_returned_on_failure():
    """The honest end of the road. A pipeline that invents a value when the
    model failed will never show you that it happened."""
    junk = text_block('{"system_name": "Half"')
    client = FakeClient(*[FakeMessage(stop_reason="end_turn", content=[junk])] * 3)
    with pytest.raises(SchemaRetryError):
        classify("A vendor description.", client=client)


# --- 3. Prompt caching ------------------------------------------------------
# The saving itself only shows in a real response's usage, so what is testable
# offline is that the request was built correctly — which is where it goes
# wrong, because a mis-built cache marker fails SILENTLY.


def test_the_system_prompt_carries_a_cache_breakpoint():
    assert isinstance(SYSTEM_BLOCKS, list)
    assert SYSTEM_BLOCKS[-1]["cache_control"] == {"type": "ephemeral"}


def test_the_description_is_not_in_the_cached_prefix(verdict_dict):
    """Anything that varies per call must sit AFTER the breakpoint.

    Put the description in the system prompt and the prefix changes on every
    row, so the cache misses every time — and nothing tells you, because a
    cache miss is a normal, successful, fully-priced call.
    """
    good = ModelVerdict.model_validate(verdict_dict)
    client = FakeClient(FakeMessage(stop_reason="end_turn", content=[text_block(good.model_dump_json())]))
    marker = "ZZQX-unique-description-marker"

    classify(f"NavGuard. {marker}", client=client)

    sent_system = json.dumps(client.calls[0]["system"])
    assert marker not in sent_system, "the description leaked into the cached prefix"
    assert marker in json.dumps(client.calls[0]["messages"])


def test_a_short_system_prompt_warns_instead_of_silently_not_caching():
    with pytest.warns(UserWarning, match="cache minimum"):
        cached_system("too short to cache")


def test_the_real_system_prompt_is_above_the_cache_minimum():
    # If this ever goes red, caching stopped working and the cost went up ~10x
    # on every call after the first, with no error anywhere.
    assert len(SYSTEM_BLOCKS[-1]["text"]) > 2048 * 4


# --- 4. Cost arithmetic -----------------------------------------------------


def test_cache_reads_are_a_tenth_of_the_input_price():
    fresh = price(usage(input_tokens=10_000, output_tokens=0), "claude-haiku-4-5")
    cached = price(
        usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=10_000),
        "claude-haiku-4-5",
    )
    assert cached.total_usd == pytest.approx(fresh.total_usd * 0.10)


def test_the_first_call_of_a_session_shows_a_negative_saving():
    """Caching costs a premium to write and only pays from the second call on.

    Reporting the write as a saving would flatter the number, which is exactly
    the kind of figure that ends up in a README and cannot be defended.
    """
    first = price(usage(input_tokens=100, cache_creation_input_tokens=7_000), "claude-haiku-4-5")
    assert first.cache_saved_usd < 0

    later = price(usage(input_tokens=100, cache_read_input_tokens=7_000), "claude-haiku-4-5")
    assert later.cache_saved_usd > 0
    assert later.total_usd < first.total_usd


def test_an_unpriced_model_raises_rather_than_defaulting():
    """A silently mispriced call is worse than a crash: it produces a number
    that looks like evidence."""
    with pytest.raises(UnknownModelError):
        price(usage(), "claude-something-new-5")


def test_billed_input_counts_every_bucket():
    cost = price(
        usage(input_tokens=300, cache_creation_input_tokens=0, cache_read_input_tokens=6_900),
        "claude-haiku-4-5",
    )
    assert cost.billed_input_tokens == 7_200


def test_summarise_totals_a_batch():
    costs = [price(usage(input_tokens=1_000), "claude-haiku-4-5") for _ in range(3)]
    total = summarise(costs)
    assert total["calls"] == 3
    assert total["total_usd"] == pytest.approx(sum(c.total_usd for c in costs))
    assert summarise([])["calls"] == 0


# --- 5. The cost log must not be able to store what was pasted --------------


def test_log_call_writes_a_length_not_the_text(tmp_path, verdict_dict):
    """The no-logging promise is made on the page and in the README. It is only
    true if it is true here, so it is asserted rather than assumed."""
    from toolkit.costlog import log_call

    secret = "Jane Doe, employee number 4471, performance review"
    result = SimpleNamespace(
        usage=usage(), model="claude-haiku-4-5", attempts=1, stop_reason="end_turn"
    )
    target = tmp_path / "call_log.jsonl"

    line = log_call(result, latency_s=1.2, char_count=len(secret), path=target, to_stdout=False)

    written = target.read_text(encoding="utf-8")
    assert secret not in written
    assert "Jane" not in written
    assert line["char_count"] == len(secret)
    assert json.loads(written.strip())["char_count"] == len(secret)


def test_log_call_has_no_parameter_that_could_take_the_description():
    """A structural guard, not a behavioural one. If someone adds a `text=` or
    `description=` parameter to make debugging easier, this fails and the
    conversation happens before it ships rather than after."""
    import inspect

    from toolkit.costlog import log_call

    params = set(inspect.signature(log_call).parameters)
    assert not params & {"description", "text", "prompt", "input", "output", "content"}


# --- 5b. Spend cap ----------------------------------------------------------
# A public paste box wired to a personal API key is an unbounded bill with a
# text area in front of it. Nothing in Cloud Run limits what a request costs.


def test_the_spend_cap_stops_the_next_call_and_returns_429(monkeypatch):
    """The endpoint must read the CONFIGURED cap, not one passed at the call site.

    The first version of this test spent $2 and asserted on `check_spend_cap(cap=1.0)`,
    which passed — while the endpoint went on using the module default of $5,
    reached the real client and failed on a missing API key. The test was wrong
    and the failure said so. Patching the configured value is what actually
    proves the endpoint is wired to the cap.
    """
    from fastapi.testclient import TestClient

    import toolkit.costlog as costlog
    from webapp.main import app

    monkeypatch.setattr(costlog, "SPEND_CAP_USD", 1.0)
    costlog.reset_spend()
    try:
        costlog.check_spend_cap()  # nothing spent yet: must not raise
        costlog.record_spend(price(usage(input_tokens=2_000_000), "claude-haiku-4-5"))  # $2
        with pytest.raises(costlog.SpendCapExceeded):
            costlog.check_spend_cap()

        # 429, not 402 or 503: this is rate limiting, the limiter is spend
        # rather than requests, and a client that backs off is doing right.
        response = TestClient(app).post("/classify", json={"description": "A vendor tool."})
        assert response.status_code == 429
        assert "cap" in response.json()["detail"]
    finally:
        costlog.reset_spend()


def test_a_cap_of_zero_disables_the_check():
    """The local-development setting, explicit rather than an absent variable."""
    from toolkit.costlog import check_spend_cap, record_spend, reset_spend

    reset_spend()
    try:
        record_spend(price(usage(input_tokens=2_000_000), "claude-haiku-4-5"))
        check_spend_cap(cap=0)  # must not raise
    finally:
        reset_spend()


def test_no_api_error_response_repeats_what_was_pasted():
    """Regression, 2026-09-10. The first version of the request model used
    Pydantic's max_length=. Pydantic puts the offending value in the error's
    `input` field and FastAPI serialises the whole error list into the 422
    body, so an over-long paste came straight back to the caller — and would
    have reached any tool watching 4xx responses. Nothing in the code looked
    wrong; only asserting on the response body found it.

    Every error path is checked, not just that one, because the leak was not a
    property of the length rule. It was a property of returning error objects
    built by someone else.
    """
    from fastapi.testclient import TestClient

    from webapp.main import app

    secret = "CONFIDENTIAL-CLIENT-NAME-ACME-SICAV"
    client = TestClient(app)

    responses = [
        client.post("/classify", json={"description": f"{secret} " + "x" * 9_000}),
        client.post("/classify", json={"description": "   "}),
        client.post("/classify", json={"description": 12345}),
        client.post("/classify", json={"not_the_field": secret}),
    ]
    for response in responses:
        assert response.status_code >= 400
        assert secret not in response.text, f"input leaked in a {response.status_code}"
        assert "xxxxxxxxxx" not in response.text


def _failures_that_quote_the_input(secret: str) -> list[BaseException]:
    """The exceptions a classification can end in, each carrying the input.

    Pydantic's message quotes the rejected value (`input_value='...'`), and a
    model-filled field can be a near-copy of the description. An SDK error can
    quote the request body it sent. The refusal case is here because the
    prompt is ours, not the model's — nothing to leak — and asserting on it
    keeps the list honest when a new exception type is added.
    """
    from toolkit.structured import Usage

    spent = Usage()
    spent.add(usage())
    return [
        SchemaRetryError(
            3,
            f"1 validation error for ModelVerdict\nrisk_tier\n  Input should be ... "
            f"[type=enum, input_value='{secret}', input_type=str]",
            usage=spent,
            model="claude-haiku-4-5",
        ),
        RefusalError("The model refused.", usage=spent, model="claude-haiku-4-5"),
        RuntimeError(f"Error code: 400 - {{'request': {{'description': '{secret}'}}}}"),
    ]


def test_no_error_from_the_model_path_repeats_what_was_pasted(monkeypatch):
    """Regression, 2026-09-15. The test above covered the input guards and
    stopped there; the review found the 502 body carrying Pydantic's
    validation text with the rejected value inside it. Same shape of bug as
    2026-09-10 — an error object built by someone else, returned whole."""
    from fastapi.testclient import TestClient

    import toolkit.costlog as costlog
    import webapp.main as main

    secret = "CONFIDENTIAL-CLIENT-NAME-ACME-SICAV"
    for failure in _failures_that_quote_the_input(secret):

        def fail(description, **kwargs):
            raise failure

        monkeypatch.setattr(main, "classify_with_meta", fail)
        costlog.reset_spend()
        response = TestClient(main.app).post("/classify", json={"description": "A vendor tool."})
        assert response.status_code >= 400
        assert secret not in response.text, f"{type(failure).__name__} leaked into the API body"
    costlog.reset_spend()


def test_no_message_the_ui_shows_repeats_what_was_pasted():
    """The Streamlit page showed str(exc) for every exception. Same list of
    failures, same sentinel, checked against the one function the page now
    goes through instead of a rendered page."""
    from webapp.errors import ApiError, safe_error_message

    secret = "CONFIDENTIAL-CLIENT-NAME-ACME-SICAV"
    for failure in _failures_that_quote_the_input(secret):
        assert secret not in safe_error_message(failure), type(failure).__name__

    # The two texts written by this codebase pass through unchanged — an
    # ApiError's detail IS the API's safe message, and the cap message names
    # dollar amounts, never input.
    assert safe_error_message(ApiError("cap reached")) == "cap reached"


# --- 6. The Act gates that are decided in Python ----------------------------
# These are the regulatory edge cases from START-HERE's Day 3 list. The part of
# each that Python decides is tested here, deterministically and for free; the
# part the model decides is in the live tests below. Splitting them this way
# means a regression in our own gate logic is caught on every commit.


def test_annex_iii_5b_fraud_carve_out_creates_no_article_6_4_duty():
    """SentinelPay: a fraud/AML tool that scores natural persons.

    The carve-out is written into the Annex III 5(b) entry itself, so the
    system was never in Annex III. That is NOT an Article 6(3) derogation, and
    the distinction matters because a derogation creates its own documentation
    duty under Article 6(4) and a carve-out does not. Confusing the two is the
    single most likely wrong answer this tool can give.
    """
    duties = obligations_for(
        RiskTier.MINIMAL_RISK,
        Role.DEPLOYER,
        False,
        ["Annex III 5(b)"],
        derogation=AnnexIIIDerogation.NONE,
        performs_profiling=True,
    )
    joined = " ".join(duties)
    assert "6(4)" not in joined, "a carve-out must not produce an Article 6(4) duty"


def test_an_article_6_3_derogation_does_produce_an_article_6_4_duty():
    """InterviewScribe: in Annex III, lifted out by Article 6(3)(d).

    The mirror of the test above. If both produced the same obligations, the
    tool would not be distinguishing the two mechanisms at all — and both
    tests would still pass individually.
    """
    duties = obligations_for(
        RiskTier.MINIMAL_RISK,
        Role.DEPLOYER,
        True,
        ["Annex III 4(a)", "Article 6(3)(d)"],
        derogation=AnnexIIIDerogation.PREPARATORY_TASK,
        performs_profiling=False,
    )
    assert any("6(4)" in duty for duty in duties), (
        "an Article 6(3) derogation carries its own documentation duty"
    )


def test_article_25_escalates_a_deployer_to_provider_only_on_the_high_risk_path():
    """All three Article 25(1) triggers are tied to high-risk systems.

    Reading it more broadly would make every re-badged minimal-risk tool a
    provider obligation — the mirror-image error of the one the gate fixes.
    """
    escalated = Classification.derive_effective_role(
        Role.DEPLOYER, Art25Trigger.NAME_OR_TRADEMARK, RiskTier.HIGH_RISK
    )
    assert escalated is Role.PROVIDER

    not_escalated = Classification.derive_effective_role(
        Role.DEPLOYER, Art25Trigger.NAME_OR_TRADEMARK, RiskTier.MINIMAL_RISK
    )
    assert not_escalated is Role.DEPLOYER


def test_the_stated_role_is_never_overwritten_by_the_escalation(verdict_dict):
    """The delta between stated and effective is auditable, and Day 13 needs to
    score "did it spot the escalation" separately from "did it get the role"."""
    verdict_dict["art25_trigger"] = "name_or_trademark_on_high_risk_system"
    record = Classification.from_verdict(ModelVerdict.model_validate(verdict_dict))
    assert record.our_role is Role.DEPLOYER
    assert record.effective_role is Role.PROVIDER


def test_every_record_carries_the_ruleset_version_and_a_date():
    """A row with no ruleset version cannot be re-checked after the Act moves,
    and the Act has moved once already (the Digital Omnibus, 27 July 2026)."""
    record = Classification.from_verdict(
        ModelVerdict.model_validate(
            {
                "system_name": "NavGuard",
                "provider_name": None,
                "system_purpose": "Flags anomalous NAV movements.",
                "act_applies": "applies",
                "exclusion_ground": "none",
                "our_role": "provider",
                "art25_trigger": "none",
                "risk_tier": "minimal_risk",
                "annex_iii_derogation": "none",
                "performs_profiling": False,
                "is_gpai": False,
                "gpai_note": None,
                "legal_basis": [],
                "rationale": "Not a listed Annex III use.",
                "gaps": [],
                "confidence": "high",
            }
        )
    )
    assert record.ruleset_version.startswith("v2-")
    assert record.classified_at is not None


# --- 7. Live model behaviour ------------------------------------------------
# The four cases from START-HERE's Day 3 list that only the model can answer.
# Run with:  pytest -m live
#
# These assert on what must NOT happen, not on an exact tier. The tool's known
# weakness (notes/day3.md pattern A) is over-confidence, so an assertion that
# pins an exact answer would be re-testing today's behaviour rather than the
# rule underneath it.


@pytest.mark.live
def test_gibberish_does_not_get_a_confident_tier():
    record = classify("asdkfj qwe 8837 ;; zzz")
    assert record.risk_tier is RiskTier.INSUFFICIENT_INFORMATION
    assert record.confidence.value in {"low", "medium"}
    assert record.gaps, "an insufficient_information verdict must say what is missing"


@pytest.mark.live
def test_a_non_ai_vendor_is_not_dressed_up_as_high_risk():
    record = classify(
        "DeskBook. A room-booking tool for our Luxembourg office. Staff pick a "
        "desk from a floor plan and the booking is written to a calendar. No "
        "recommendations, no scoring, no machine learning of any kind."
    )
    assert record.risk_tier is not RiskTier.HIGH_RISK
    assert not record.performs_profiling


@pytest.mark.live
def test_a_fraud_detection_tool_must_not_come_back_high_risk():
    """The Annex III 5(b) carve-out. The surrounding language is all money,
    risk and regulation, which is exactly what pulls a model toward high_risk."""
    record = classify(
        "SentinelPay. Screens incoming subscription and redemption instructions "
        "and scores each investor's transaction pattern for money-laundering and "
        "payment fraud indicators, raising alerts to the financial crime team "
        "for investigation. Vendor-hosted, used as supplied."
    )
    assert record.risk_tier is not RiskTier.HIGH_RISK
    assert record.annex_iii_derogation is AnnexIIIDerogation.NONE, (
        "the 5(b) exception is a carve-out, not an Article 6(3) derogation"
    )


@pytest.mark.live
def test_an_annex_iii_system_that_profiles_is_not_derogated():
    """The Article 6(3) final-subparagraph override: profiling beats every limb."""
    record = classify(
        "ShortlistPro. Reads each applicant's CV and scores them from 1 to 100 on "
        "fit for the role, then ranks the applicants so the hiring manager can "
        "start at the top. Used for first-round screening on all operations roles."
    )
    assert record.performs_profiling is True
    assert record.risk_tier is RiskTier.HIGH_RISK
    assert record.annex_iii_derogation is AnnexIIIDerogation.NONE
