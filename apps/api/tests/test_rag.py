"""Document parsing, chunking, hybrid retrieval, ACLs and grounded answering."""

import io

import docx
import pytest

from app.ai.providers.mock import HashingEmbeddingProvider
from app.rag.chunking import chunk_pages
from app.rag.parsing import ParsedPage, UnsupportedFile, parse, safe_filename, sniff
from tests.helpers import POLICY_DOC, SECRET_DOC


def test_sniff_rejects_spoofed_and_unknown_types():
    with pytest.raises(UnsupportedFile):
        sniff("evil.pdf", b"MZ\x90\x00 not a pdf")
    with pytest.raises(UnsupportedFile):
        sniff("run.exe", b"MZ")
    with pytest.raises(UnsupportedFile):
        sniff("fake.docx", b"PK\x03\x04garbage")
    assert sniff("ok.txt", b"hello") == "text/plain"


def test_safe_filename_strips_paths():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\x\\a<b>.txt") == "a_b_.txt"


def test_docx_parsing_and_chunking():
    d = docx.Document()
    d.add_heading("Leave policy", 1)
    for i in range(30):
        d.add_paragraph(f"Paragraph {i}: employees accrue holiday at a rate of two days per month of service.")
    buf = io.BytesIO()
    d.save(buf)
    ctype = sniff("leave.docx", buf.getvalue())
    pages = parse(ctype, buf.getvalue())
    chunks = chunk_pages(pages, chunk_size=400, overlap=80)
    assert len(chunks) > 3
    assert all(len(c.content) <= 600 for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunk_overlap_preserves_context():
    text = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(60))
    chunks = chunk_pages([ParsedPage(None, text)], chunk_size=300, overlap=60)
    assert len(chunks) > 2
    assert chunks[0].content.splitlines()[-1] in chunks[1].content


def test_hashing_embeddings_are_deterministic_and_semantic():
    e = HashingEmbeddingProvider(384)
    (a, b, c), _ = e.embed(["expense claims submission deadline", "deadline for submitting expense claims",
                            "kubernetes cluster autoscaling"])
    dot = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731
    assert dot(a, b) > dot(a, c)
    assert e.embed(["same"])[0] == e.embed(["same"])[0]


@pytest.fixture
def assistant(client, world):
    h, a = world["h"], str(world["a"].id)
    app = client.post("/api/v1/apps", json={"organisation_id": a, "name": "KB"}, headers=h["engineer"]).json()
    client.patch(f"/api/v1/apps/{app['id']}", json={"status": "active"}, headers=h["engineer"])
    pub = client.post(f"/api/v1/apps/{app['id']}/documents", files={"file": ("expense-policy.md", io.BytesIO(POLICY_DOC),
                                                                             "text/markdown")},
                      data={"visibility": "organisation"}, headers=h["engineer"])
    assert pub.status_code == 201, pub.text
    sec = client.post(f"/api/v1/apps/{app['id']}/documents", files={"file": ("board.txt", io.BytesIO(SECRET_DOC),
                                                                             "text/plain")},
                      data={"visibility": "restricted"}, headers=h["engineer"])
    return {"app": app, "public": pub.json(), "secret": sec.json()}


def test_ingestion_creates_chunks(client, world, assistant):
    docs = client.get(f"/api/v1/apps/{assistant['app']['id']}/documents", headers=world["h"]["engineer"]).json()
    assert {d["status"] for d in docs} == {"ready"}
    assert all(d["chunk_count"] > 0 for d in docs)


def test_grounded_answer_with_citations(client, world, assistant):
    r = client.post(f"/api/v1/apps/{assistant['app']['id']}/chat",
                    json={"question": "Within how many days must expense claims be submitted?"}, headers=world["h"]["cust_a"])
    assert r.status_code == 200, r.text
    m = r.json()["message"]
    assert m["insufficient_evidence"] is False
    assert "30 days" in m["content"]
    assert m["citations"] and m["citations"][0]["filename"] == "expense-policy.md"
    assert "[1]" in m["content"]


def test_insufficient_evidence_refusal(client, world, assistant):
    r = client.post(f"/api/v1/apps/{assistant['app']['id']}/chat",
                    json={"question": "What is the capital of Australia and its population?"}, headers=world["h"]["cust_a"])
    m = r.json()["message"]
    assert m["insufficient_evidence"] is True and m["citations"] == []
    assert "could not find enough information" in m["content"]


def test_single_incidental_term_match_is_refused(client, world, assistant):
    """Regression: 'next year' matching unrelated sentences must not produce a cited, ungrounded answer."""
    r = client.post(f"/api/v1/apps/{assistant['app']['id']}/chat",
                    json={"question": "What is the share price target for next year?"}, headers=world["h"]["cust_a"])
    m = r.json()["message"]
    assert m["insufficient_evidence"] is True and m["citations"] == []


def test_restricted_document_not_retrievable_by_unlisted_customer(client, world, assistant):
    q = {"question": "What is the chief executive bonus pool percentage?"}
    cust = client.post(f"/api/v1/apps/{assistant['app']['id']}/chat", json=q, headers=world["h"]["cust_a"]).json()
    assert "14 percent" not in cust["message"]["content"]
    assert all(c["filename"] != "board.txt" for c in cust["message"]["citations"])
    assert all(x["filename"] != "board.txt" for x in cust["retrieval"])
    # explicitly granting access makes it retrievable
    alice = str(world["users"]["cust_a"].id)
    client.patch(f"/api/v1/documents/{assistant['secret']['id']}", json={"allowed_user_ids": [alice]},
                 headers=world["h"]["engineer"])
    granted = client.post(f"/api/v1/apps/{assistant['app']['id']}/chat", json=q, headers=world["h"]["cust_a"]).json()
    assert "14 percent" in granted["message"]["content"]


def test_restricted_document_hidden_from_listing_and_download(client, world, assistant):
    h = world["h"]["cust_a"]
    names = [d["filename"] for d in client.get(f"/api/v1/apps/{assistant['app']['id']}/documents", headers=h).json()]
    assert "board.txt" not in names
    assert client.get(f"/api/v1/documents/{assistant['secret']['id']}/download", headers=h).status_code == 404


def test_conversation_history_and_feedback(client, world, assistant):
    h = world["h"]["cust_a"]
    url = f"/api/v1/apps/{assistant['app']['id']}/chat"
    r1 = client.post(url, json={"question": "When must expense claims be submitted?"}, headers=h).json()
    r2 = client.post(url, json={"question": "Which travel class is required for short flights?",
                                "conversation_id": r1["conversation_id"]}, headers=h).json()
    assert r2["conversation_id"] == r1["conversation_id"]
    msgs = client.get(f"/api/v1/conversations/{r1['conversation_id']}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    fb = client.post(f"/api/v1/messages/{r2['message']['id']}/feedback", json={"rating": 1}, headers=h)
    assert fb.status_code == 200 and fb.json()["feedback"] == 1
    # other users cannot see or rate this conversation
    assert client.get(f"/api/v1/conversations/{r1['conversation_id']}/messages",
                      headers=world["h"]["admin_a"]).status_code == 404


def test_upload_validation(client, world, assistant):
    url = f"/api/v1/apps/{assistant['app']['id']}/documents"
    h = world["h"]["engineer"]
    assert client.post(url, files={"file": ("x.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}, headers=h).status_code == 415
    assert client.post(url, files={"file": ("x.pdf", io.BytesIO(b"not a pdf"), "application/pdf")}, headers=h).status_code == 415
    dup = client.post(url, files={"file": ("again.md", io.BytesIO(POLICY_DOC), "text/markdown")}, headers=h)
    assert dup.status_code == 400 and dup.json()["error"]["code"] == "duplicate_document"
    assert client.post(url, files={"file": ("x.txt", io.BytesIO(b"secret"), "text/plain")}, data={"visibility": "internal"},
                       headers=world["h"]["cust_a"]).status_code == 400


def test_telemetry_and_usage_recorded(client, world, assistant):
    h = world["h"]["cust_a"]
    client.post(f"/api/v1/apps/{assistant['app']['id']}/chat", json={"question": "When must claims be submitted?"}, headers=h)
    m = client.get("/api/v1/monitoring/overview?hours=1&source=real", headers=world["h"]["engineer"]).json()
    assert m["requests"] >= 1 and m["sources_present"].get("platform", 0) >= 1
    assert m["latency_ms"]["p95"] >= 0 and m["tokens"]["total"] > 0
    costs = client.get("/api/v1/costs/summary?days=1", headers=world["h"]["super"]).json()
    agents = {a["agent"] for a in costs["by_agent"]}
    assert {"knowledge_assistant_agent", "ingestion"} <= agents
