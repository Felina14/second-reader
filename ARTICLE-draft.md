# I built a tool that reads my documents back to me the way a blind colleague's software will. It was humbling.

*[LEAD IMAGE: the reading-order trail — the numbered red polyline zig-zagging down and back up the three columns of the sample page. This one still frame is the whole argument.]*

Look at that line.

That red line is the order a screen reader announces the page above it. Not the order I laid it out — the order it actually *gets read*. It goes all the way down the first column, then leaps back up to the top of the second, down again, back up to the third. A neat three-column layout, announced as three disconnected monologues with a lurch between each.

I made that layout. I was pleased with it. I had never once seen this line.

## The thing I kept meaning to check and never did

I send decks and documents all week. I check the spelling, I check the numbers, I check the logo is the current one. I have never checked whether the person receiving it can actually read it — because checking properly meant learning what a screen reader does to a merged table cell, and I never had the twenty minutes. So I sent it and hoped.

Every accessibility checker I'd tried gave me a list of rule numbers. "1.3.1 Info and Relationships." "1.4.3 Contrast (Minimum)." I don't know what those mean and I can't picture them, so I ignored all of them. That's the real failure mode of accessibility tooling: it's correct and it's unreadable, so nothing changes.

So I built the opposite. **Second Reader doesn't score your document. It makes you experience it.**

## What it does

You drop in a PDF. It shows you four things you can't currently see:

**1. The reading order, as audio.** It reads the page aloud in the exact order a screen reader will announce it, and highlights each word on the page as it's spoken. You *watch* your careful layout come apart in real time.

**2. That trail.** The same reading order, frozen into one image — because here's the thing I had to be honest with myself about: my best feature is audio, and nobody reads an article with the sound on. The trail carries the same insight into a still frame. It's the picture at the top of this piece.

**3. A colour-blind view**, side by side, with a slider that fades from the original to the simulation. The red/green status column I was so pleased with becomes two identical greys for roughly one in twelve men of Northern European descent.

**4. Findings in plain English** — what breaks, and what it does to the person on the other end. Not "add a header row." Instead: *"a screen-reader user hears forty numbers read out with nothing telling them which column each one belongs to."*

## Two moments that changed how I think about this

**The speed toggle.** Real screen-reader users don't listen at the pace I was imagining. They listen at 2×, 2.5×, 3×. So I added a toggle. Play the document at 2.5× and something happens to your face — you realise the experience you'd been picturing, the calm little voice, was nothing like the actual firehose people navigate every day. It's one line of code and it reframes the entire problem.

**The alt text.** Every accessibility tool on earth will tell you "this chart has no description." Mine writes the description. When it finds a figure with no alt text, it sends the image to a vision model and hands you a finished sentence, ready to paste. It turns a complaint into a deliverable. That's also the *only* place I let a generative model near this app — describing an image is genuine generation. Deciding whether something is a defect is not, so I never let the model do that. The rules fire deterministically in code; the model only ever writes prose.

## How it's built (and why it's smaller than you'd expect)

The whole thing is five AWS services and one synchronous request.

- **Amazon Textract** (`AnalyzeDocument` with the LAYOUT feature) is the core. It returns the document's blocks *in reading order*, with a bounding box for every word. That reading order is the entire ballgame — it's the gap between what I laid out and what gets announced, and everything else in the app is built on it.
- **Amazon Polly** speaks the linearised page, and — crucially — returns **word-level speech marks** with byte offsets, so I can light up the exact word being spoken without the audio and the highlight ever drifting apart.
- **Amazon Bedrock** (Nova Lite) does the two language jobs: phrasing each finding as a human consequence, and writing alt text from the figure image via its vision model.
- **AWS Lambda** behind a Function URL runs the pipeline; **Amazon S3 + CloudFront** serve the frontend and the audio. That's it.

The browser renders page one with pdf.js and sends it as an image, which sidesteps Textract's single-page-PDF limit and means the highlight boxes line up perfectly with what you see. A demo run costs well under a cent.

I originally designed this as an asynchronous Step Functions pipeline — the right shape for multi-page documents at scale, and I've kept that design documented as the roadmap. But for a single page, one synchronous path is faster, cheaper, and honest about what it is. Restraint was the better engineering decision.

## The part that's a little embarrassing

I built this and pointed it at my own recent decks. The reading order was wrong on most of them. My tables had no headers. My charts said nothing. My status colours vanished.

None of the people I sent those to could tell me, because the ones affected had already given up expecting documents to work — they'd stopped mentioning it. Which, after all these years, is a slightly embarrassing thing to admit.

You fix what you've experienced. You ignore a list of violations. That's the whole idea.

*[Try it: LIVE LINK — hit "Use sample document," turn the trail on, switch to 2.5×, and press play.]*
