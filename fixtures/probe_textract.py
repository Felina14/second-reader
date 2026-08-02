"""Feed the fixture to Textract sync AnalyzeDocument (LAYOUT) and dump reading order."""
import boto3, sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
tx = boto3.client("textract", region_name="us-east-1")

with open(os.path.join(HERE, "test.pdf"), "rb") as f:
    data = f.read()
print(f"pdf bytes: {len(data)}")

resp = tx.analyze_document(Document={"Bytes": data}, FeatureTypes=["LAYOUT"])
blocks = resp["Blocks"]
by_id = {b["Id"]: b for b in blocks}

def words_of(block):
    out = []
    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                ch = by_id.get(cid)
                if ch and ch["BlockType"] == "WORD":
                    out.append(ch["Text"])
    return out

layout = [b for b in blocks if b["BlockType"].startswith("LAYOUT_")]
print(f"\n=== {len(layout)} LAYOUT blocks in Textract reading order ===\n")
for i, b in enumerate(layout):
    bb = b["Geometry"]["BoundingBox"]
    txt = " ".join(words_of(b))[:70]
    print(f"{i:2d} {b['BlockType']:22s} L={bb['Left']:.2f} T={bb['Top']:.2f}  {txt}")

# table header check
tables = [b for b in blocks if b["BlockType"] == "TABLE"]
cells = [b for b in blocks if b["BlockType"] == "CELL"]
hdr = [c for c in cells if "COLUMN_HEADER" in c.get("EntityTypes", [])]
print(f"\nTABLE blocks: {len(tables)}  CELL blocks: {len(cells)}  COLUMN_HEADER cells: {len(hdr)}")
figs = [b for b in layout if b["BlockType"] == "LAYOUT_FIGURE"]
print(f"LAYOUT_FIGURE blocks: {len(figs)}")

json.dump(resp, open(os.path.join(HERE, "_textract_raw.json"), "w"))
print("\nraw response saved to fixtures/_textract_raw.json")
