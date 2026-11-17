"""Self-contained browser preview using real variable fonts and live axis controls."""

import base64
from io import BytesIO
import json
from fontTools.ttLib import TTFont
from specimens import ROOT

OUT = ROOT / "trials/2026-11-17-layout-optical"


def main():
    sources = json.loads((OUT / "optical-fonts.json").read_text())
    sources["system"] = json.loads((ROOT / "recipes/layout-sources.json").read_text())[
        "system"
    ]["font"]
    css = []
    sections = []
    for key in ["sans", "system", "code"]:
        f = TTFont(ROOT / sources[key])
        f.flavor = "woff2"
        b = BytesIO()
        f.save(b)
        css.append(
            "@font-face{font-family:Trial"
            + key
            + ";src:url(data:font/woff2;base64,"
            + base64.b64encode(b.getvalue()).decode()
            + ') format("woff2");font-weight:300 '
            + ("400" if key == "code" else "600")
            + ";}"
        )
        sections.append(
            '<section data-family="'
            + key
            + '"><h2>Daikonic Transit '
            + key.title()
            + (
                "</h2><p>Existing optical profiles</p>"
                if key == "system"
                else "</h2><p>Optical-size review candidate</p>"
            )
            + '<div class="controls"><label>Weight <input class="weight" type="range" min="300" max="'
            + ("400" if key == "code" else "600")
            + '" value="350" step="1"><output>350</output></label><label>Optical size <input class="optical" type="range" min="10" max="36" value="14" step="1"><output>14</output></label><label>Text size <input class="size" type="range" min="11" max="48" value="20" step="1"><output>20px</output></label></div><div class="sample" contenteditable="true" spellcheck="false" style="font-family:Trial'
            + key
            + '">Context Menu — café naïve résumé<br>q́ ẍ q́̈ í j́ ç ą ę ș<br>const snake_case = get_items([input]);<br>-> ->> => != !== <= >= :: @@</div></section>'
        )
    html = """<!doctype html><meta charset="utf-8"><title>Daikonic Transit — optical-size review</title><style>__FONTS__
*{box-sizing:border-box}body{margin:0;padding:32px;background:#eeecd9;color:#101712;font:16px system-ui}main{max-width:1200px;margin:auto}h1{font-size:28px}section{border-top:1px solid #b9b9ab;margin-top:28px;padding-top:12px}h2{color:#194454;font-size:22px}.controls{display:flex;gap:25px;flex-wrap:wrap;margin:20px 0}label{display:flex;align-items:center;gap:9px}output{min-width:42px}input{width:130px}.sample{font-size:20px;line-height:1.8;padding:20px;background:#fffdf1;white-space:pre-wrap;overflow:auto;font-feature-settings:"calt" 1,"liga" 1;font-optical-sizing:none;font-variation-settings:"wght" 350,"opsz" 14;min-height:190px}.dark{background:#101712;color:#eeecd9}.dark h2{color:#fa994a}.dark .sample{background:#202822;color:#eeecd9}button{padding:8px 12px}p{max-width:850px;line-height:1.5}</style><main><h1>Daikonic Transit — optical-size review</h1><p>Compare the optical-size endpoints while keeping the text size fixed. At optical size14, Sans and Code retain their current default drawings. These are separate review fonts; they do not replace installed fonts. Click the samples to edit them.</p><button id="theme">Toggle light / dark</button>__SECTIONS__<p id="status">Loading embedded fonts…</p></main><script>
for(const section of document.querySelectorAll('section')){const sample=section.querySelector('.sample');function update(){const weight=section.querySelector('.weight'),optical=section.querySelector('.optical'),size=section.querySelector('.size');sample.style.fontVariationSettings='"wght" '+weight.value+', "opsz" '+optical.value;sample.style.fontSize=size.value+'px';for(const input of section.querySelectorAll('input'))input.nextElementSibling.value=input.value+(input.className==='size'?'px':'');}for(const input of section.querySelectorAll('input'))input.addEventListener('input',update);update();}
document.querySelector('#theme').onclick=()=>document.body.classList.toggle('dark');Promise.all(['sans','system','code'].map(x=>document.fonts.load('20px Trial'+x))).then(x=>{document.body.dataset.fontStatus=JSON.stringify(x.map(v=>v.length>0));document.querySelector('#status').textContent=x.every(v=>v.length>0)?'All three embedded variable fonts loaded.':'A font failed to load.';});
</script>""".replace(
        "__FONTS__", "".join(css)
    ).replace(
        "__SECTIONS__", "".join(sections)
    )
    (OUT / "Interactive.html").write_text(html)
    print(OUT / "Interactive.html")


if __name__ == "__main__":
    main()
