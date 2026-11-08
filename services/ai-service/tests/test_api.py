from conftest import SECRET, signed_headers


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_classify(client):
    r = client.post("/classify", json={"text": "I want a refund for the double charge"})
    assert r.status_code == 200
    assert r.json() == {"category": "billing", "urgency": "low", "sentiment": "neutral"}
    assert r.headers["X-Request-ID"]


def test_request_id_propagates(client):
    r = client.post("/classify", json={"text": "hi"}, headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_redact_endpoint(client):
    r = client.post("/redact", json={"text": "I'm Maria Lopez, maria@x.com"})
    assert r.json()["redacted"] == "I'm [NAME], [EMAIL]"
    r = client.post("/redact?llm_pass=false", json={"text": "I'm Maria Lopez, maria@x.com"})
    assert r.json()["redacted"] == "I'm Maria Lopez, [EMAIL]"


def test_answer(client):
    r = client.post("/answer", json={"question": "How do I reset my password?"})
    assert r.status_code == 200
    assert r.json()["sources"][0]["file"] == "account.md"


def test_validation_error(client):
    assert client.post("/classify", json={"text": ""}).status_code == 422


def test_webhook_rejects_bad_signature(client):
    body, headers = signed_headers({"ticket_id": "t1", "body": "x"}, secret="wrong")
    assert client.post("/webhook/ticket", content=body, headers=headers).status_code == 401
    assert client.post("/webhook/ticket", json={"ticket_id": "t1", "body": "x"}).status_code == 401


def test_webhook_auto_reply_and_pii_never_stored(client, fake_llm):
    payload = {"ticket_id": "t1", "subject": "Login help",
               "body": "I'm Maria Lopez (maria@x.com, 305-555-0142). How do I reset my password?"}
    body, headers = signed_headers(payload)
    r = client.post("/webhook/ticket", content=body, headers=headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["route"] == "auto_reply"
    assert d["pii_counts"] == {"NAME": 1, "EMAIL": 1, "PHONE": 1}
    assert "maria@x.com" not in d["redacted_text"] and "Maria" not in d["redacted_text"]
    # the classifier only ever saw redacted text
    assert all("maria@x.com" not in call for call in fake_llm.calls[1:])
    stored = client.get("/tickets").json()
    assert len(stored) == 1 and "maria@x.com" not in str(stored)


def test_webhook_escalates_outage(client):
    body, headers = signed_headers({"ticket_id": "t2", "body": "Everything is down, total outage!"})
    d = client.post("/webhook/ticket", content=body, headers=headers).json()
    assert d["route"] == "escalate" and d["suggested_reply"] is None


def test_webhook_queue_and_digest(client):
    for i, text in enumerate(["What colors do you sell?", "Total outage now"]):
        body, headers = signed_headers({"ticket_id": f"q{i}", "body": text})
        client.post("/webhook/ticket", content=body, headers=headers)
    dg = client.get("/tickets/digest").json()
    assert dg["total"] == 2
    assert dg["by_route"] == {"escalate": 1, "queue": 1}


def test_webhook_malformed_json(client):
    import time

    from app.security import sign

    body = b'{"ticket_id": 1'
    t = str(int(time.time()))
    r = client.post("/webhook/ticket", content=body, headers={"X-Timestamp": t, "X-Signature": sign(SECRET, t, body)})
    assert r.status_code == 422
