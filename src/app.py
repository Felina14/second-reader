"""
Second Reader - single synchronous Lambda (v2 architecture).

  PDF bytes (base64 JSON POST)
    -> Textract AnalyzeDocument (sync, LAYOUT + TABLES)
    -> linearise: blocks -> reading-order sequence + word boxes  (§4)
    -> deterministic findings                                    (§5)
    -> Polly SynthesizeSpeech x2 (mp3 + word marks)              (§4)
    -> map speech marks -> word timeline (audio & highlight can't drift)
    -> Bedrock Nova Lite: phrasing only, never invents findings  (§5)
    -> JSON { sequence, timeline, findings, audioUrl }

process() is importable so it can be exercised locally (see fixtures/run_local.py)
without deploying. The Lambda handler is a thin wrapper.
"""
import json
import os
import base64
import uuid

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET = os.environ.get("RESULTS_BUCKET")            # if unset -> return audio inline (local mode)
VOICE = os.environ.get("POLLY_VOICE", "Joanna")
NOVA_MODEL = os.environ.get("NOVA_MODEL", "amazon.nova-lite-v1:0")

textract = boto3.client("textract", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION) if BUCKET else None


# --------------------------------------------------------------------------- #
# Textract traversal helpers
# --------------------------------------------------------------------------- #
def _children(block, by_id, want):
    out = []
    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                ch = by_id.get(cid)
                if ch and ch["BlockType"] == want:
                    out.append(ch)
    return out


def _words_in_reading_order(layout_block, by_id):
    """LAYOUT -> LINE -> WORD. Return [(text, bbox[l,t,w,h]), ...] in order."""
    words = []
    for line in _children(layout_block, by_id, "LINE"):
        for w in _children(line, by_id, "WORD"):
            bb = w["Geometry"]["BoundingBox"]
            words.append((w["Text"], [round(bb["Left"], 5), round(bb["Top"], 5),
                                      round(bb["Width"], 5), round(bb["Height"], 5)]))
    # some layouts (rare) attach WORD directly
    if not words:
        for w in _children(layout_block, by_id, "WORD"):
            bb = w["Geometry"]["BoundingBox"]
            words.append((w["Text"], [round(bb["Left"], 5), round(bb["Top"], 5),
                                      round(bb["Width"], 5), round(bb["Height"], 5)]))
    return words


def _table_dims(blocks, by_id):
    """Return (n_tables, has_any_column_header, rows, cols) from TABLES feature output."""
    tables = [b for b in blocks if b["BlockType"] == "TABLE"]
    has_header = False
    rows = cols = 0
    for t in tables:
        cells = _children(t, by_id, "CELL")
        for c in cells:
            rows = max(rows, c.get("RowIndex", 0))
            cols = max(cols, c.get("ColumnIndex", 0))
            if "COLUMN_HEADER" in c.get("EntityTypes", []):
                has_header = True
    return len(tables), has_header, rows, cols


# --------------------------------------------------------------------------- #
# Linearise + build the spoken stream (SSML) from the SAME sequence
# --------------------------------------------------------------------------- #
def linearise(blocks):
    by_id = {b["Id"]: b for b in blocks}
    layout = [b for b in blocks if b["BlockType"].startswith("LAYOUT_")]

    n_tables, has_header, trows, tcols = _table_dims(blocks, by_id)

    sequence = []          # for the frontend: blocks + word boxes
    spoken = []            # ordered tokens: {"t": word, "gi": globalIndex|None}
    gi = 0                 # global index of REAL words (highlight targets)

    def say(text):
        for tok in text.split():
            spoken.append({"t": tok, "gi": None})

    for seq_i, b in enumerate(layout):
        bt = b["BlockType"]
        real = _words_in_reading_order(b, by_id)

        # narration prefix per structural type (§4)
        if bt in ("LAYOUT_TITLE", "LAYOUT_SECTION_HEADER"):
            say("Heading.")
        elif bt == "LAYOUT_TABLE":
            say(f"Table with {trows or '?'} rows and {tcols or '?'} columns.")
        elif bt == "LAYOUT_FIGURE":
            say("Image. No description available.")
        elif bt == "LAYOUT_LIST":
            say(f"List. {len(real)} items.")
        elif bt == "LAYOUT_FOOTER":
            say("Footer.")

        block_words = []
        for text, bbox in real:
            block_words.append({"i": gi, "t": text, "bbox": bbox})
            spoken.append({"t": text, "gi": gi})
            gi += 1

        bb = b["Geometry"]["BoundingBox"]
        sequence.append({
            "seq": seq_i,
            "type": bt,
            "bbox": [round(bb["Left"], 5), round(bb["Top"], 5),
                     round(bb["Width"], 5), round(bb["Height"], 5)],
            "text": " ".join(t for t, _ in real),
            "words": block_words,
        })

    meta = {"n_tables": n_tables, "has_header": has_header,
            "trows": trows, "tcols": tcols, "n_words": gi}
    return sequence, spoken, meta


# Narration cue words after which a natural pause reads well. Breaks add no word
# marks and offsets are tracked explicitly, so alignment is unaffected either way.
_BREAK_AFTER = {"Heading.", "Footer.", "available.", "columns."}


def build_ssml(spoken):
    """Build SSML and record each spoken token's UTF-8 byte span within it, so Polly
    word marks (which carry byte offsets into the input) can be mapped back exactly."""
    buf = "<speak>"
    spans = []
    for idx, tok in enumerate(spoken):
        buf += " " if idx else ""
        start = len(buf.encode("utf-8"))
        buf += tok["t"]
        spans.append((start, len(buf.encode("utf-8"))))
        if tok["t"] in _BREAK_AFTER:
            buf += ' <break time="450ms"/>'
    buf += "</speak>"
    return buf, spans


# --------------------------------------------------------------------------- #
# Deterministic findings (§5). Detect in code; model only phrases later.
# --------------------------------------------------------------------------- #
def detect_findings(blocks, sequence, meta):
    findings = []
    layout = [b for b in blocks if b["BlockType"].startswith("LAYOUT_")]

    if any(b["type"] == "LAYOUT_FIGURE" for b in sequence):
        findings.append({"rule": "figure_no_description", "severity": "High",
                         "detail": "A figure/chart has no text description."})

    if meta["n_tables"] > 0 and not meta["has_header"]:
        findings.append({"rule": "table_no_header", "severity": "High",
                         "detail": f"A {meta['trows']}x{meta['tcols']} table has no header row."})

    # Reading order leaps back UP the page between consecutive announced words —
    # the signature of a multi-column layout being read one full column at a time.
    flat = [wd for b in sequence for wd in b["words"]]  # already in announce order
    leaps = sum(1 for a, b in zip(flat, flat[1:]) if (a["bbox"][1] - b["bbox"][1]) > 0.10)
    if leaps >= 2:
        findings.append({"rule": "reading_order_columns", "severity": "High",
                         "detail": f"Reading order leaps back up the page {leaps} times; "
                                   "the layout is announced one full column at a time."})

    for prev, nxt in zip(sequence, sequence[1:]):
        pl, pt = prev["bbox"][0], prev["bbox"][1]
        nl, nt = nxt["bbox"][0], nxt["bbox"][1]
        if (pt - nt) > 0.15 and (pl - nl) > 0.15:
            findings.append({"rule": "reading_order_jump", "severity": "High",
                             "detail": "Reading order jumps up and to the left "
                                       f"(block {prev['seq']} to {nxt['seq']})."})
            break

    if not any(b["type"] == "LAYOUT_TITLE" for b in sequence):
        findings.append({"rule": "no_title", "severity": "Medium",
                         "detail": "The page has no title block."})

    inner = layout[1:-1] if len(layout) > 2 else []
    if any(b["BlockType"] in ("LAYOUT_HEADER", "LAYOUT_FOOTER") for b in inner):
        findings.append({"rule": "chrome_in_flow", "severity": "Low",
                         "detail": "A header or footer sits in the middle of the reading flow."})

    return findings


# --------------------------------------------------------------------------- #
# Bedrock Nova Lite: phrasing ONLY. Never adds/removes/reorders findings.
# --------------------------------------------------------------------------- #
def phrase_findings(findings):
    if not findings:
        return findings
    prompt = (
        "You are helping an author about to send a document. Below is a JSON array of "
        "accessibility problems already detected by deterministic checks. For EACH one, "
        "in the SAME ORDER, write ONE sentence addressed to the author that states the "
        "human CONSEQUENCE for the person relying on a screen reader or who is colour "
        "blind — what actually goes wrong for them when they open this. Name the "
        "experience, not the rule. Do not say 'add alt text' or 'improve accessibility'; "
        "say what breaks. Be concrete and a little pointed. "
        "Do NOT add, remove, or reorder findings. Return ONLY a JSON array of strings, "
        "same length as the input.\n\n"
        "Example — instead of 'Add a header row to the table', write 'A screen reader "
        "reads out forty numbers in a row with nothing telling the listener which "
        "column each one belongs to.'\n\n"
        f"Findings: {json.dumps([{'rule': f['rule'], 'detail': f['detail']} for f in findings])}"
    )
    try:
        resp = bedrock.invoke_model(
            modelId=NOVA_MODEL,
            body=json.dumps({
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 400, "temperature": 0.2},
            }),
        )
        text = json.loads(resp["body"].read())["output"]["message"]["content"][0]["text"]
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "", 1).strip()
        phrases = json.loads(text)
        if isinstance(phrases, list) and len(phrases) == len(findings):
            for f, p in zip(findings, phrases):
                f["message"] = p.strip()
            return findings
    except Exception as e:  # noqa: BLE001 - phrasing is best-effort, never blocks
        print("phrasing failed, using deterministic detail:", repr(e))
    for f in findings:
        f["message"] = f["detail"]
    return findings


# The ONE place a generative model belongs here: describing an image is real
# generation, not a judgement. Detection stays deterministic; this only writes prose.
def generate_alt_text(png_bytes):
    resp = bedrock.converse(
        modelId=NOVA_MODEL,
        messages=[{"role": "user", "content": [
            {"image": {"format": "png", "source": {"bytes": png_bytes}}},
            {"text": "This image appears in a business document with no alt text, so "
                     "a screen-reader user is told nothing about it. Write ONE concise, "
                     "factual sentence of alt text describing what it shows and its key "
                     "takeaway. Do not begin with 'Image of' or 'A picture of' — just the "
                     "description."}]}],
        inferenceConfig={"maxTokens": 120, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


# --------------------------------------------------------------------------- #
# Polly x2 + speech-mark -> word-index timeline
# --------------------------------------------------------------------------- #
# Sync SynthesizeSpeech caps at 3,000 billed characters. A dense page can exceed
# that, so we chunk the spoken stream, synthesise each chunk, concatenate the mp3s
# (raw Polly mp3 has no header, so byte-concat is a valid continuous stream) and
# offset each chunk's word-mark times by the running audio duration.
POLLY_BILLED_LIMIT = 2400  # safety margin under 3,000


def _chunk_tokens(spoken):
    chunks, cur, cur_len = [], [], 0
    for tok in spoken:
        tlen = len(tok["t"]) + 1
        if cur and cur_len + tlen > POLLY_BILLED_LIMIT:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(tok)
        cur_len += tlen
    if cur:
        chunks.append(cur)
    return chunks


def _synth_chunk(tokens):
    import bisect
    ssml, spans = build_ssml(tokens)
    starts = [s for s, _ in spans]
    mp3 = polly.synthesize_speech(Text=ssml, TextType="ssml", OutputFormat="mp3",
                                  VoiceId=VOICE, Engine="neural")["AudioStream"].read()
    marks_raw = polly.synthesize_speech(Text=ssml, TextType="ssml", OutputFormat="json",
                                        SpeechMarkTypes=["word"], VoiceId=VOICE,
                                        Engine="neural")["AudioStream"].read()
    marks = [json.loads(l) for l in marks_raw.decode("utf-8").splitlines() if l.strip()]
    time_for_token, last = {}, 0
    for m in marks:
        k = bisect.bisect_right(starts, m["start"]) - 1
        if 0 <= k < len(spans) and spans[k][0] <= m["start"] < spans[k][1]:
            time_for_token.setdefault(k, m["time"])
        last = max(last, m["time"])
    return mp3, time_for_token, last, len(marks)


def speak(spoken):
    chunks = _chunk_tokens(spoken)
    mp3_parts, timeline = [], []
    offset_ms, total_marks = 0, 0
    for tokens in chunks:
        mp3, time_for_token, last, nmarks = _synth_chunk(tokens)
        mp3_parts.append(mp3)
        total_marks += nmarks
        for k, tok in enumerate(tokens):
            if tok["gi"] is not None and k in time_for_token:
                timeline.append({"ms": offset_ms + time_for_token[k], "gi": tok["gi"]})
        offset_ms += last + 450  # running audio position (last word + trailing pause)
    return b"".join(mp3_parts), timeline, {
        "chunks": len(chunks), "marks": total_marks,
        "spoken": len(spoken), "tokens_timed": len(timeline)}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def process(pdf_bytes, run_id=None):
    run_id = run_id or uuid.uuid4().hex[:12]
    resp = textract.analyze_document(Document={"Bytes": pdf_bytes},
                                     FeatureTypes=["LAYOUT", "TABLES"])
    blocks = resp["Blocks"]

    sequence, spoken, meta = linearise(blocks)
    findings = detect_findings(blocks, sequence, meta)
    findings = phrase_findings(findings)
    mp3, timeline, align = speak(spoken)

    result = {
        "runId": run_id,
        "page": {"aspect": _page_aspect(blocks)},
        "sequence": sequence,
        "timeline": timeline,
        "findings": findings,
        "meta": {**meta, **align},
    }

    if BUCKET:
        key = f"audio/{run_id}.mp3"
        s3.put_object(Bucket=BUCKET, Key=key, Body=mp3, ContentType="audio/mpeg")
        result["audioUrl"] = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=900)
    else:
        result["audioBase64"] = base64.b64encode(mp3).decode()

    return result


def _page_aspect(blocks):
    for b in blocks:
        if b["BlockType"] == "PAGE":
            bb = b["Geometry"]["BoundingBox"]
            return round(bb["Height"] / bb["Width"], 4) if bb["Width"] else 1.294
    return 1.294  # US letter default


# --------------------------------------------------------------------------- #
# Lambda Function URL handler
# --------------------------------------------------------------------------- #
# CORS is handled entirely by the Function URL's CORS config. The handler must NOT
# add its own Access-Control-* headers, or the response carries duplicate
# Access-Control-Allow-Origin headers and browsers reject it ("Load failed").
def _reply(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"},
            "body": body if isinstance(body, str) else json.dumps(body)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return _reply(200, "{}")
    try:
        raw = event.get("body", "") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        payload = json.loads(raw)
        # Second action: write alt text for a cropped figure ('altFor' = base64 PNG).
        if payload.get("altFor"):
            return _reply(200, {"alt": generate_alt_text(base64.b64decode(payload["altFor"]))})
        # Frontend sends page 1 rendered to PNG ('image'); 'pdf' kept for compatibility.
        data = base64.b64decode(payload.get("image") or payload["pdf"])
        if len(data) > 5 * 1024 * 1024:
            return _reply(413, {"error": "Rendered page exceeds 5 MB (sync Textract limit)."})
        return _reply(200, process(data))
    except textract.exceptions.UnsupportedDocumentException:
        return _reply(415, {"error": "Textract couldn't read this page format. "
                                     "Try a different document."})
    except Exception as e:  # noqa: BLE001
        print("handler error:", repr(e))
        return _reply(500, {"error": str(e)})
