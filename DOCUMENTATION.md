# Second Reader — Complete Documentation

*You proofread it. Nobody read it the way they're about to.*

---

## 1. What it is

**Second Reader** is a web app that shows you a document **the way a screen-reader
user and a colour-blind reader will actually experience it — before you send it.**

Every other accessibility checker hands you rule numbers (`1.3.1 Info and
Relationships`, `1.4.3 Contrast`). Those are correct and unreadable, so nothing
changes. Second Reader's thesis is the opposite:

> **Every other checker hands you rule numbers. This hands you the experience.**

You upload a PDF of any length. It gives you what you cannot currently see — and then
fixes it:

| # | Output | What it reveals / does |
|---|--------|-----------------|
| 1 | **Reading-order audio** | The whole document read aloud in the exact order a screen reader announces it, across every page. |
| 2 | **Word-level synced highlighting** | Each word lights up on the page as Polly speaks it — you *watch* a multi-column layout come apart. On multi-page documents the viewer follows the audio page to page. |
| 3 | **Reading-order trail** | A numbered polyline over each page, freezing the announcement order into one still image (the zigzag). |
| 4 | **Colour-blind view** | The same page under deuteranopia / protanopia / tritanopia, with an original↔simulated crossfade slider. |
| 5 | **Plain-English findings** | What breaks and the *human consequence* — plus **generated alt text** for figures, ready to paste. |
| 6 | **Accessible version (remediation agent)** | A Bedrock agent rebuilds the document as clean semantic HTML — one reading order, real headings, a table with header cells, images with alt text. |
| 7 | **Voice / text editing** | Speak or type an addition and the agent applies it to the accessible document. |
| 8 | **Multi-format download** | The fixed document as HTML, Markdown, or plain text. |

Two touches that reframe the problem:
- **Screen-reader speed toggle (1× / 1.75× / 2.5×)** — real screen-reader users listen at 2–3×. Hearing it at 2.5× is visceral in a way no rule number is.
- **Alt-text generation** — it doesn't just report "figure has no description"; a vision model *writes* the description. A complaint becomes a deliverable.

---

## 2. Design principles

1. **Detect deterministically; generate only where generation belongs.** Whether
   something is a defect — and the document's structure, reading order, and word
   geometry — is decided by deterministic tools (rules in code + Textract), never a
   model. The language model is used only for pure generation: (a) phrasing each
   finding as a human consequence, (b) writing alt text for an image, (c) rebuilding
   the document as accessible HTML, (d) applying voice/text edits. It can never invent,
   remove, or reorder a finding. (This is also why **extraction stays on Textract**,
   not a vision LLM: we need exact per-word bounding boxes for the highlight and trail,
   determinism for trust, and a *literal* linearisation that surfaces the failure
   rather than a "smart" reader that hides it.)
2. **The insight must survive as a still image.** The killer feature is audio, but
   the thing usually shared (an article, a screenshot) is silent. The reading-order
   trail carries the same insight into a frame.
3. **Consequence, not compliance.** Findings say "a screen-reader user hears forty
   numbers with nothing telling them which column each belongs to," not "add a
   header row."
4. **Restraint as engineering.** A single synchronous Lambda (looping Textract per
   page) beats an elaborate async pipeline for documents of this size. The async
   Step Functions design is kept as the documented scale path, not built.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser  (static site: HTML + pdf.js + canvas, no framework)         │
│                                                                        │
│   1. pdf.js renders EVERY page to <canvas>                             │
│   2. each canvas → JPEG → base64 ───────POST {images:[…]}────┐          │
│   3. colour-blind sim + reading-order trail drawn locally    │         │
│   4. pager + highlighter follow the audio across pages        │        │
└──────────────────────────────────────────────────────────────┼────────┘
                                                                 │  HTTPS
        served over HTTPS by                                     ▼
   ┌──────────────────────┐          ┌────────────────────────────────────────┐
   │ CloudFront + S3 (OAC) │          │  AWS Lambda (Function URL) — 4 actions  │
   │  private site bucket  │          │  one function, zip + boto3              │
   └──────────────────────┘          │                                         │
                                      │  analyse (images): for each page →      │
   returns JSON:                      │    Textract AnalyzeDocument (LAYOUT+TAB) │
   { pages[], timeline,  ◀────────────┤    linearise → per-page seq + words     │
     findings, audioUrl }             │    deterministic findings (aggregated)  │
                                      │    Polly ×N → mp3 + word speech marks   │
   { alt }  ◀─ POST {altFor} ─────────┤    byte-offset map → one word timeline  │
   { html } ◀─ POST {remediate} ──────┤  alt:       Bedrock Nova vision         │
   { html } ◀─ POST {edit} ───────────┤  remediate: Bedrock Nova → a11y HTML    │
                                      │  edit:      Bedrock Nova applies change  │
                                      └──────────────┬──────────────────────────┘
                                                     │ mp3 → S3 (presigned, 1d TTL)
                                                     ▼
                                            ┌────────────────────┐
                                            │  S3 results bucket  │
                                            └────────────────────┘
```

**Why the browser sends page images, not the PDF:** sync Textract `AnalyzeDocument`
only accepts a single-page PDF or an image. Rendering each page client-side and
sending it as a compressed JPEG sidesteps multi-page PDFs, odd encodings, and the
5 MB PDF limit; fits many pages in one request; and the word bounding boxes line up
perfectly because Textract sees the exact pixels displayed.

---

## 4. AWS services used

| Service | Role in the app | Key detail |
|---|---|---|
| **Amazon Textract** | The core, called once per page. `AnalyzeDocument` (sync) with `FeatureTypes=['LAYOUT','TABLES']`. | LAYOUT returns blocks **in reading order** with a bounding box per word; TABLES gives cells + `COLUMN_HEADER` entities for the header-row check. |
| **Amazon Polly** | Speaks the whole linearised document. `SynthesizeSpeech` ×2 per chunk — once `mp3`, once `json` with `SpeechMarkTypes=['word']`. Neural engine, voice Joanna. | Word speech marks carry **byte offsets**, used to sync highlight to audio without drift. SSML is chunked under the sync limit and byte-concatenated. |
| **Amazon Bedrock** | Four pure-generation jobs, model **Nova Lite** (`amazon.nova-lite-v1:0`). | (a) `InvokeModel` phrases findings as consequences; (b) `Converse`+**image** writes alt text (vision); (c) `Converse` rebuilds the doc as accessible HTML (remediation); (d) `Converse` applies a spoken/typed edit. |
| **AWS Lambda** | One Python 3.12 function (zip + boto3) behind a **Function URL** (HTTPS, no API Gateway). | Runs the whole synchronous pipeline; **four actions**: analyse (`images`), alt-text (`altFor`), remediate, edit. |
| **Amazon S3** | Two private buckets: results (mp3) and site (frontend). | Block-public-access on; audio via presigned URL (15 min); 1-day lifecycle expiry on audio. |
| **Amazon CloudFront** | Serves the frontend over HTTPS with **Origin Access Control** to the private site bucket. | So the whole app lives in AWS — nothing runs from a laptop. |
| **AWS SAM / CloudFormation** | Infrastructure as code — one `template.yaml` deploys everything. | Stack name `second-reader`. |
| **Amazon CloudWatch** | Lambda logs (automatic). | Used for debugging during the build. |

Region: **us-east-1** for everything (safest for Nova; avoids cross-region issues).

---

## 5. The workflow, end to end

### A. Upload → analysis (all pages)
1. User drops a PDF or picks one with **Choose PDF**.
2. **pdf.js** renders **every page** (capped at 15) to a canvas at scale 2 (~150 dpi);
   each page is exported as a compressed **JPEG**.
3. The JPEGs are base64-encoded and `POST`ed as `{images:[…]}` to the **Lambda Function URL**.
4. **Lambda** loops the pages: `AnalyzeDocument(Document={'Bytes': jpeg}, FeatureTypes=['LAYOUT','TABLES'])` per page.

### B. Linearisation (`linearise`, the heart of it)
Textract returns blocks already in reading order. For each `LAYOUT_*` block:
- Walk `LAYOUT → LINE → WORD` relationships to collect every word with its text and
  normalised bounding box, in order. A running **global index** `gi` is assigned to
  every real word — and it **continues across pages** (page 2 starts where page 1
  left off), so the one audio timeline spans the whole document. That index is what
  the highlighter drives off.
- Build a **spoken-token stream** in parallel: structural narration cues
  (`"Heading."`, `"Table with N rows and M columns."`, `"Image. No description
  available."`, `"Footer."`) tagged with `gi=None`, then the block's real words
  tagged with their `gi`. Audio and highlight come from the **same sequence**, so
  they cannot drift apart.

Emitted `sequence` (per block): `{seq, type, bbox, text, words:[{i, t, bbox}]}`.

### C. Findings (`detect_findings`, deterministic)
| Rule | Trigger | Severity |
|---|---|---|
| `figure_no_description` | any `LAYOUT_FIGURE` present | High |
| `table_no_header` | a `TABLE` with no `CELL` carrying `EntityTypes=['COLUMN_HEADER']` | High |
| `reading_order_columns` | ≥2 upward "leaps" (next word's top < prev word's top by >0.10 of page height) — the multi-column signature | High |
| `reading_order_jump` | a block whose successor is up-and-left by >0.15 | High |
| `no_title` | zero `LAYOUT_TITLE` | Medium |
| `chrome_in_flow` | a `LAYOUT_HEADER/FOOTER` in the middle of the sequence | Low |
| `colour_only_status` | **client-side**: a saturated red and green that converge under the daltonisation matrix (ΔE-style distance < 45) | High |

Findings are detected **per page**, then aggregated by rule across the document
(`_aggregate_findings`): a rule firing on several pages appears once, noting the pages
(e.g. *"…(pages 1, 3)"*). Then **one** Bedrock Nova call rewrites each finding as a
human consequence. The prompt forbids adding, removing, or reordering, and the
response is rejected unless its length equals the input length (falls back to the
deterministic wording). The **colour-only** finding is detected client-side by
scanning every page's pixels.

### D. Speech + timeline (`speak`)
- The spoken stream is chunked into **sub-3,000-billed-character** pieces (Polly's
  sync limit). Each chunk → SSML → `SynthesizeSpeech` twice (mp3 + word marks).
- **Byte-offset mapping:** while building each chunk's SSML, every token's UTF-8
  byte span is recorded. Each Polly word mark (which carries a byte `start`) is
  mapped to the token whose span contains it. This is immune to Polly splitting a
  token (e.g. `1,240`) into several marks or skipping punctuation — no positional
  drift.
- Chunk MP3s are byte-concatenated into one continuous stream (raw Polly mp3 has no
  header). Each chunk's word times are offset by the running audio position, giving
  a single monotonic `timeline: [{ms, gi}]`.

### E. Response
```json
{ "runId": "...",
  "pages": [{"pageNumber":1, "aspect":1.29, "sequence":[...]}, ...],
  "timeline": [{"ms":1517,"gi":0}, ...],   // one timeline across all pages
  "findings": [{"rule","severity","detail","message"}, ...],
  "audioUrl": "https://…s3…/audio/<run>.mp3?<presigned>",
  "meta": {"pageCount","chunks","marks","spoken","tokens_timed","n_words"} }
```
The mp3 is written to the results bucket and returned as a presigned URL.

### F. In the browser
- **Pager:** the frontend keeps every page's rendered canvas. A ‹ Page X of N ›
  pager switches pages; during playback the highlighter **auto-switches** to whatever
  page is being announced (each timeline word knows its page).
- **Highlighter:** a `requestAnimationFrame` loop reads `audio.currentTime`, binary-
  searches `timeline` for the current `gi`, and draws the word's box on an overlay
  canvas (and highlights it in the whole-document transcript). rAF (not `timeupdate`)
  gives smooth word-level tracking.
- **Reading-order trail:** per current page — words are reduced to one point per line
  (line centroids), connected in announcement order as a red polyline, with a numbered
  node at each block start. Toggleable; drawn beneath the live highlight.
- **Colour-blind view:** the current page is drawn to a canvas, `getImageData`, a
  per-pixel sRGB simulation matrix applied, `putImageData`; a slider crossfades
  original↔simulated. Entirely client-side.
- **Speed toggle:** sets `audio.playbackRate` with `preservesPitch=true`, so speech
  stays natural-pitch and the highlighter stays in sync automatically (it reads
  media time, not wall-clock).
- **Alt text:** for a figure finding, the browser crops the figure's bbox from its
  page canvas and `POST`s it as `{altFor: <png>}`. Lambda runs Bedrock **vision**
  (`Converse` with an image block) and returns one sentence, shown with a Copy button.

### G. Remediation — the accessible version (`remediate` action)
The frontend sends the analysed structure (every page's blocks + the generated alt
text + the findings) as `{remediate:{…}}`. A Bedrock Nova call rebuilds it as clean
semantic HTML: one logical single-column reading order, `<h1>/<h2>`, `<p>`, a real
`<table>` with `<thead>`/`<th scope="col">` (column names inferred), `<figure><img
alt>` using the alt text, and a `<footer>` for chrome. The model only re-tags existing
content; it never invents facts. The HTML is rendered in a clean "document" card.

### H. Voice / text editing (`edit` action)
In the accessible-version card, a mic button (Web Speech API) or text field lets the
user say/type an addition — e.g. *"add a one-line summary at the top."* The transcript
plus the current HTML go to Bedrock as `{edit:{html, instruction}}`; Nova returns the
updated HTML, which re-renders in place. The mic falls back to the text field where
the browser has no speech recognition.

### I. Multi-format download
The rendered accessible document is converted **client-side** to **HTML**, **Markdown**
(headings, list items, a Markdown table, `![alt]`), or **plain text** (headings
upper-cased, table rows tab-separated) and downloaded — no extra server call.

---

## 6. Colour-blindness simulation matrices

Viénot/Brettel-derived sRGB approximations applied per pixel (client-side):

```
Deuteranopia (~6% of men)      Protanopia                  Tritanopia
r' = .625r + .375g             r' = .567r + .433g          r' = .95r + .05g
g' = .70r  + .30g              g' = .558r + .442g          g' = .433g + .567b
b' = .30g  + .70b              b' = .242g + .758b          b' = .475g + .525b
```

These are simulation *approximations*, not a clinical model.

---

## 7. Repository layout

```
SecondReader/
├── template.yaml                       SAM: S3 (results + site), Lambda + Function URL,
│                                       CloudFront + OAC, scoped IAM
├── src/
│   └── app.py                          The entire backend:
│                                         handler (4 actions) + process() [multi-page loop]
│                                         + linearise + detect_findings + _aggregate_findings
│                                         + phrase_findings + build_ssml + speak [chunked]
│                                         + generate_alt_text + remediate + edit_doc
├── frontend/
│   ├── index.html                      Whole UI: pdf.js (all pages), pager, rAF highlighter,
│   │                                   trail, colour-blind, speed, findings, alt text,
│   │                                   remediation, voice/text edit, multi-format download
│   └── test.pdf                        sample the app can load
├── fixtures/
│   ├── make_fixture.py                 builds the adversarial single-page test.pdf
│   ├── make_trail_image.py            renders the reading-order trail as a standalone image
│   ├── probe_textract.py              dumps Textract reading order (first validation step)
│   ├── run_local.py                   runs the full pipeline locally, no deploy
│   ├── test.pdf                       the adversarial deck
│   └── trail-lead.png                 generated lead visual
├── Second-Reader-sample.pdf           one-page sample to upload
├── Second-Reader-sample-multipage.pdf two-page sample (pager follows the audio)
├── README.md                          quick start / run / redeploy / teardown
├── DOCUMENTATION.md                   this file
└── ARTICLE-draft.md                   publish-ready write-up (trail as lead image)
```

---

## 8. Deployed resources

After `sam deploy`, the stack prints these outputs (names are generated per account):

- **App:** the CloudFront distribution domain (`SiteUrl` output)
- **Function URL:** the Lambda Function URL (`FunctionUrl` output)
- **Stack:** `second-reader` · **Results bucket:** `ResultsBucket` output · **Site bucket:** `SiteBucket` output

Read them any time with:
```bash
aws cloudformation describe-stacks --stack-name second-reader \
  --query 'Stacks[0].Outputs' --output table
```

---

## 9. Build & deploy

```bash
export AWS_PROFILE=<your-profile> AWS_REGION=us-east-1

python3 fixtures/make_fixture.py          # (re)build the adversarial sample
python3 fixtures/run_local.py             # run the whole pipeline locally, no deploy

sam build && sam deploy --stack-name second-reader --resolve-s3 \
  --capabilities CAPABILITY_IAM --no-confirm-changeset          # backend + infra

SITE=$(aws cloudformation describe-stacks --stack-name second-reader \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucket'].OutputValue" --output text)
aws s3 cp frontend/index.html s3://$SITE/index.html \
  --content-type text/html --cache-control no-cache             # push frontend
# → open the SiteUrl output
```

Paste the `FunctionUrl` stack output into `FN_URL` in `frontend/index.html` before
uploading (and again if a redeploy ever changes it).

---

## 10. Cost

Per demo run: Textract LAYOUT ~$0.015/page, Polly neural ~$16/1M chars (a page is a
rounding error), Nova Lite fractions of a cent, S3/Lambda/CloudFront within free
tier. **A run costs well under a cent.**

**Teardown:**
```bash
# empty both buckets first (names from stack outputs), then delete the stack
sam delete --stack-name second-reader --no-prompts --region us-east-1
```

---

## 11. Notable engineering decisions (the build journey)

- **Validated Textract's reading order first**, against a real fixture, before
  building anything on it (`probe_textract.py`). Discovered LAYOUT blocks link to
  `LINE` then `WORD`, and that the table header check needs the `TABLES` feature.
- **Byte-offset speech-mark mapping** replaced naive positional zipping after Polly
  split comma-numbers into extra marks — the fix that made highlight sync drift-proof.
- **Simplified from async to sync.** The v1 design used Step Functions + SNS task
  tokens + EventBridge for async Textract. For a single page, one synchronous Lambda
  is faster and cheaper; the async design is retained only as the scale path.
- **CORS gotcha:** the Lambda was adding its own `Access-Control-Allow-Origin` on top
  of the Function URL's, producing duplicate headers that browsers reject ("Load
  failed"). Fix: let the Function URL own CORS entirely.
- **PNG-not-PDF:** switched the client to send a rendered page image, fixing
  `UnsupportedDocumentException` on multi-page PDFs.
- **Chunked Polly:** dense pages exceeded Polly's 3,000-char sync limit
  (`TextLengthExceededException`); the fix chunks, concatenates audio, and offsets
  the timeline.
- **Added a failure, not a feature:** a single-column doc proves nothing, so the
  sample was rebuilt as an adversarial page and the reading-order trail was added to
  make the collapse legible in one frame.
- **Multi-page:** switched the client to render *every* page and send compressed
  JPEGs (Textract reads JPEG; JPEG keeps many pages under the request limit), with a
  continuous cross-page word timeline and a pager that follows the audio.
- **Remediation over reporting:** added a Bedrock agent that rebuilds the document as
  accessible HTML — "…and here it is fixed" — plus voice/text editing and HTML/
  Markdown/text export. Chose a Bedrock **model invocation** over the managed Bedrock
  Agents service (same output, ships now, no heavy provisioning).
- **Vision for generation, not extraction:** kept Textract for structure/geometry
  (exact per-word boxes, determinism, and a literal linearisation that *reveals* the
  failure); used vision only to describe and rebuild.
- **`InvalidSsmlException`:** document text with `&`, `<`, `>` (e.g. "R&D") broke the
  SSML; each spoken token is now XML-escaped, with the byte-span map measured on the
  escaped text so highlight sync stays exact.
```
