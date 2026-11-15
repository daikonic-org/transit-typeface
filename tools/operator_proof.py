"""Show standalone operators beside their ligatures at named/intermediate weights."""

from io import BytesIO
import json

import uharfbuzz as hb
from adopt_weighting import ROOT, instance
from specimens import DATA, Panel


def main():
    cfg = DATA["families"]["code"]
    fragments = []
    labels = Panel("operator-label", DATA["families"]["sans"])
    labels.text("TRANSIT CODE / OPERATOR CONSISTENCY", 26, 34, 24, 400, "#194454")
    labels.text("Previous", 26, 68, 15, 400, "#194454")
    labels.text(
        "Adopted72% letters / tuned operators retained", 810, 68, 15, 400, "#194454"
    )
    for i, w in enumerate([300, 325, 350, 375, 400]):
        y = 102 + i * 155
        labels.text("Weight " + str(w), 26, y, 13, 400, "#194454")
        for side, x in [("previous", 26), ("adopted", 810)]:
            p = Panel(f"op-{w}-{side}", cfg)
            f = instance(
                ROOT / cfg["weighting_baseline" if side == "previous" else "font"],
                w,
                None,
            )
            stream = BytesIO()
            f.save(stream)
            h = hb.Font(hb.Face(stream.getvalue()))
            h.scale = (1000, 1000)
            p.instances[w] = (f, h)
            p.text("=  ==  ===   !=  !==  <=  >=", x, y + 41, 30, w, "#101712")
            p.text("->  ->>  =>  <-  <<-  ::  :; .", x, y + 79, 26, w, "#101712")
            p.elements.append(
                f'<rect x="{x-5}" y="{y+94}" width="758" height="35" fill="#11191D"/>'
            )
            p.text(
                "r = value; a == b; a === b; -> result",
                x + 5,
                y + 116,
                16,
                w,
                "#EEECD9",
            )
            fragments.append(p.body())
    fragments.insert(0, labels.body())
    out = ROOT / ".build/accepted-weighting/proofs"
    (out / "OperatorConsistency.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="895" viewBox="0 0 1600 895"><rect width="1600" height="895" fill="#EEECD9"/>'
        + "".join(fragments)
        + "</svg>"
    )
    p = out / "pages.json"
    pages = json.loads(p.read_text())
    pages = [v for v in pages if v["name"] != "OperatorConsistency"]
    pages.append({"name": "OperatorConsistency", "width": 1600, "height": 895})
    p.write_text(json.dumps(pages, indent=2) + "\n")
    print("Generated standalone/ligature consistency proof")


if __name__ == "__main__":
    main()
