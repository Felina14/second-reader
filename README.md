# Second Reader

> **You proofread it. Nobody read it the way they're about to.**

Second Reader opens a document the way the recipient's **assistive technology** will
open it — and hands it back to you *before* you send it. It reads the page aloud in
the order a screen reader announces it, highlights each word as it's spoken, shows
the page as a colour-blind reader sees it, and explains what breaks in plain English.

> Built for the AWS Builder Center weekend challenge — *turn one annoying task into an app.*

---

## The annoying task

The pre-send accessibility check everyone means to do and nobody does — because doing
it properly means learning what a screen reader does to a merged table cell. So we
send the deck and hope. And every accessibility checker gives back a list of rule
numbers (`1.3.1`, `1.4.3`) that are impossible to picture, so they get ignored.

**Second Reader's whole idea: every other checker hands you rule numbers. This hands
you the experience.**

## What it does

Upload a PDF and get back five things you can't currently see:

1. **Reading-order audio** — the page read aloud in the exact order a screen reader announces it.
2. **Word-level synced highlighting** — each word lights up on the page as it's spoken.
3. **Reading-order trail** — a numbered line over the page showing the announcement order zig-zag across a multi-column layout (the whole point, in one still image).
4. **Colour-blind view** — the same page under deuteranopia / protanopia / tritanopia, with an original↔simulated slider.
5. **Plain-English findings** — what breaks and the *human consequence*, plus **generated alt text** for figures, ready to paste.

Plus a **screen-reader speed toggle** (1× / 1.75× / 2.5×) — because real screen-reader
users listen at 2–3×, and hearing it is the moment it lands.

## The one feature that makes it stand out

It **shows you instead of scolding you.** You *hear* your careful three-column layout
collapse into nonsense, and the reading-order trail freezes that collapse into a
single image. You fix what you've experienced; you ignore a list of violations.

---

## Demo

- **Live app:** https://d2tlyziog3y8ws.cloudfront.net
- **Sample document:** `Second-Reader-sample.pdf` — a one-page deck that packs every failure at once (three mis-linearising columns, a table with no header, a chart with no alt text, a red/green status column). Drag it onto the app, or click **Use sample document**.

![Reading-order trail](fixtures/trail-lead.png)

*The red line is the order a screen reader announces the page: down column one, then a
leap back up to column two, then column three. A neat layout, announced as three
disconnected monologues.*

---

## AWS services used

| Service | Role |
|---|---|
| **Amazon Textract** | `AnalyzeDocument` (sync) with `FeatureTypes=['LAYOUT','TABLES']` — returns blocks **in reading order** with a bounding box per word, and table cells for the header-row check. The core of the app. |
| **Amazon Polly** | `SynthesizeSpeech` ×2 (neural) — one MP3, one JSON with word **speech marks**, used to sync the highlight to the audio without drift. |
| **Amazon Bedrock** | Nova Lite — phrases each finding as a human consequence, and (vision) writes alt text from a figure image. Generation only, never judgement. |
| **AWS Lambda** | One Python function behind a **Function URL** runs the whole synchronous pipeline. |
| **Amazon S3** | Two private buckets — generated audio, and the static frontend. |
| **Amazon CloudFront** | Serves the frontend over HTTPS via Origin Access Control. |
| **AWS SAM / CloudFormation** | One `template.yaml` deploys everything. |

Everything runs in **us-east-1**.

## How it works

```
Browser (pdf.js renders page 1 → PNG)         Lambda (Function URL)
     │  POST { image }                     ┌─▶ Textract  AnalyzeDocument (LAYOUT+TABLES)
     ▼                                     │   linearise → sequence + word boxes
  CloudFront + S3 ──serves the site        │   deterministic findings
     ▲                                     │   Polly ×2 → mp3 + word speech marks
     │  { sequence, timeline,              │   byte-offset map → word timeline
     │    findings, audioUrl } ◀───────────┤   Bedrock Nova → phrasing
     │  { alt } ◀──POST { altFor }─────────┘   Bedrock Nova (vision) → alt text
     ▼                                         mp3 → S3 (presigned URL)
  highlighter · trail · colour-blind · speed · findings
```

The browser sends page 1 as a **PNG**, not the raw PDF — that sidesteps sync
Textract's single-page limit (so any multi-page PDF works) and keeps the highlight
boxes aligned with exactly what's on screen.

Full technical detail — linearisation, the speech-mark byte-offset alignment, the
findings rules, the colour matrices, the build decisions — is in
[`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## Deploy it yourself

**Prerequisites:** an AWS account, AWS CLI configured, [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html),
Python 3.12+, and **Bedrock model access to Amazon Nova Lite** enabled in us-east-1.

```bash
export AWS_PROFILE=<your-profile> AWS_REGION=us-east-1

# 1. deploy backend + hosting (S3, Lambda + Function URL, CloudFront)
sam build && sam deploy --guided --stack-name second-reader
#   ^ first run only; accept defaults. Note the FunctionUrl and SiteUrl outputs.

# 2. paste the FunctionUrl output into FN_URL in frontend/index.html

# 3. push the frontend to the site bucket
SITE=$(aws cloudformation describe-stacks --stack-name second-reader \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucket'].OutputValue" --output text)
aws s3 cp frontend/index.html s3://$SITE/index.html --content-type text/html --cache-control no-cache
aws s3 cp frontend/test.pdf   s3://$SITE/test.pdf   --content-type application/pdf --cache-control no-cache

# 4. open the SiteUrl output in your browser
```

Local development (no deploy needed):

```bash
python3 fixtures/make_fixture.py   # (re)build the adversarial sample PDF
python3 fixtures/run_local.py      # run the whole pipeline locally against it
python3 -m http.server 8000        # then open http://localhost:8000/frontend/index.html
```

## Cost

A demo run costs **well under a cent** — Textract LAYOUT ~$0.015/page, Polly neural
~$16 per million characters (a page is a rounding error), Nova Lite fractions of a
cent, and S3/Lambda/CloudFront within free tier.

**Teardown:** empty the two buckets, then `sam delete --stack-name second-reader`.

## Repository layout

```
src/app.py            the entire backend (Textract → linearise → findings → Polly → Bedrock)
template.yaml         SAM: buckets, Lambda + Function URL, CloudFront + OAC, scoped IAM
frontend/index.html   the whole UI (pdf.js, highlighter, trail, colour-blind, speed, findings)
fixtures/             the adversarial sample + local test/validation scripts
DOCUMENTATION.md      full technical reference
```

---

*Design principle throughout: detection is deterministic (rules in code); the language
model is used only to write prose — phrasing findings and describing images — never to
decide whether something is a defect.*
