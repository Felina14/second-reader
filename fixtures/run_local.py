"""Exercise the full pipeline locally (no deploy). Writes fixtures/out.mp3 + out.json."""
import sys, os, json, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.pop("RESULTS_BUCKET", None)  # force local (inline audio) mode
import app

HERE = os.path.dirname(os.path.abspath(__file__))
pdf = open(os.path.join(HERE, "test.pdf"), "rb").read()
r = app.process(pdf, run_id="local")

open(os.path.join(HERE, "out.mp3"), "wb").write(base64.b64decode(r.pop("audioBase64")))
# out.json keeps a single flat "sequence" (page 1) for the other fixture scripts
r_out = dict(r)
r_out["sequence"] = r["pages"][0]["sequence"]
json.dump(r_out, open(os.path.join(HERE, "out.json"), "w"), indent=2)

print("=== meta ===", r["meta"])
for p in r["pages"]:
    print(f"\n=== page {p['pageNumber']} ({len(p['sequence'])} blocks) ===")
    for b in p["sequence"]:
        print(f"  seq {b['seq']:2d} {b['type']:20s} words={len(b['words']):3d}  {b['text'][:50]}")
print(f"\n=== timeline: {len(r['timeline'])} highlight events ===")
print("  first 5:", r["timeline"][:5])
print(f"\n=== findings ({len(r['findings'])}) ===")
for f in r["findings"]:
    print(f"  [{f['severity']:6s}] {f['rule']}")
    print(f"           {f.get('message')}")
print("\nwrote fixtures/out.mp3 and fixtures/out.json")
