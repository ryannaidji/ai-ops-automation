from app.models import Classification
from app.routing import decide
from app.security import sign, verify

BODY = b'{"ticket_id":"1"}'


def test_valid_signature():
    assert verify("s", "1000", sign("s", "1000", BODY), BODY, now=1000)


def test_wrong_secret_or_tampered_body():
    sig = sign("s", "1000", BODY)
    assert not verify("other", "1000", sig, BODY, now=1000)
    assert not verify("s", "1000", sig, BODY + b" ", now=1000)


def test_replay_window_and_missing_headers():
    sig = sign("s", "1000", BODY)
    assert not verify("s", "1000", sig, BODY, now=1000 + 301)
    assert not verify("s", None, sig, BODY)
    assert not verify("s", "1000", None, BODY)
    assert not verify("s", "abc", sig, BODY)


def c(cat="account", urg="low", sent="neutral"):
    return Classification(category=cat, urgency=urg, sentiment=sent)


def test_routing_rules():
    assert decide(c(urg="high"), "some answer")[0] == "escalate"
    assert decide(c(urg="medium", sent="negative"), "ans")[0] == "escalate"
    assert decide(c(), "Use Forgot password.")[0] == "auto_reply"
    assert decide(c(), "I don't know based on the knowledge base.")[0] == "queue"
    assert decide(c(cat="feedback"), "Thanks!")[0] == "queue"
    assert decide(c(), None)[0] == "queue"
