"""Draw isolated, unadopted Book-weight lifetime-marker candidates."""
from pathlib import Path
import hashlib
import json
import argparse
import pathops
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.svgPathPen import SVGPathPen

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'releases/2026.11.18.2/code/VF/DaikonicTransitCode-VF.ttf'
parser = argparse.ArgumentParser(description=__doc__)
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--kite', action='store_true')
mode.add_argument('--horizontal', action='store_true')
args = parser.parse_args()
font = instantiateVariableFont(TTFont(SOURCE), {'wght':350}, inplace=False)
gs = font.getGlyphSet()

def polygon(points):
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo(points[0])
    for point in points[1:]: pen.lineTo(point)
    pen.closePath()
    return p

def rectangle(x0,y0,x1,y1):
    return polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])

def diamond(x,y,r):
    return polygon([(x,y+r),(x+r,y),(x,y-r),(x-r,y)])

def union(a,b):
    return pathops.op(a,b,pathops.PathOp.UNION)

quote = pathops.Path()
gs['quoteleft'].draw(TransformPen(quote.getPen(),(1.2,0,0,1.2,-60,-137.6)))
solid = union(diamond(300,595,105),rectangle(268,420,332,595))
hollow = pathops.op(diamond(300,595,105),diamond(300,595,37),pathops.PathOp.DIFFERENCE)
hollow = union(hollow,rectangle(268,420,332,544))
flag = union(polygon([(195,600),(405,700),(405,500)]),rectangle(341,420,405,700))
candidates = [('A','Curved quote',quote),('B','Diamond + stem',solid),('C','Open diamond',hollow),('D','Half-diamond flag',flag)]
if args.kite:
    candidates = [
        (letter, name, polygon([(300,700),(405,595),(300,595-depth),(195,595)]))
        for letter, name, depth in [('E','Short kite',150),('F','Medium kite',190),('G','Long kite',230)]
    ]
    title = 'Lifetime marker — kite study'
    subtitle = 'Book 350 · same upper diamond and width · three lower-point lengths'
    basename = 'Lifetime-Kites'
elif args.horizontal:
    # Retain only the l's lower hook; the cut stem becomes a plain far terminal.
    original = pathops.Path()
    gs['l'].draw(original.getPen())
    original = pathops.simplify(original)
    cropped = pathops.op(original, rectangle(-1000,-1000,2000,600),pathops.PathOp.INTERSECTION)
    candidates = []
    for letter, name, mirror, growth in [
        ('H','Hook left',False,0), ('I','Hook right',True,0)
    ]:
        rotated = pathops.Path()
        scale = .45
        matrix = (0,-scale, -scale if mirror else scale,0,0,0)
        cropped.draw(TransformPen(rotated.getPen(),matrix))
        if growth:
            stroke = pathops.Path(rotated)
            stroke.stroke(growth,pathops.LineCap.BUTT_CAP,pathops.LineJoin.MITER_JOIN,2.5)
            rotated = union(rotated,pathops.simplify(stroke))
        x0,y0,x1,y1 = rotated.bounds
        aligned = pathops.Path()
        rotated.draw(TransformPen(aligned.getPen(),(1,0,0,1,300-(x0+x1)/2,700-y1)))
        candidates.append((letter,name,aligned))
    title = 'Lifetime marker — horizontal hook study'
    subtitle = 'Book 350 · one downward hook · plain opposite terminal'
    basename = 'Lifetime-Horizontal'
else:
    title = 'Lifetime marker — isolated design study'
    subtitle = 'Daikonic Transit Code · Book 350 · four candidates for review'
    basename = 'Lifetime-Markers'
paths = []
for letter,name,path in candidates:
    pen = SVGPathPen(None)
    path.draw(pen)
    paths.append((letter,name,pen.getCommands()))

svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="900" viewBox="0 0 960 900">',
       '<rect width="960" height="900" fill="#eeeddb"/>',
       '<style>text{font-family:Arial,sans-serif;fill:#172331}.label{font-size:16px}.small{font-size:12px;fill:#53616a}</style>',
       f'<text x="40" y="44" font-size="26" font-weight="bold">{title}</text>',
       f'<text x="40" y="73" class="label">{subtitle}</text>',
       '<defs>']
for letter,name,d in paths:
    svg.append(f'<path id="{letter}" d="{d}"/>')
svg.append('</defs>')

def use(letter,x,top,size,fill='#172331'):
    scale=size/1000
    svg.append(f'<use href="#{letter}" xlink:href="#{letter}" xmlns:xlink="http://www.w3.org/1999/xlink" transform="translate({x-300*scale} {top+700*scale}) scale({scale} {-scale})" fill="{fill}"/>')

centers = [300,660] if args.horizontal else [220,480,740] if args.kite else [170,380,590,800]
for (letter,name,d),x in zip(paths,centers):
    svg.append(f'<text x="{x}" y="118" text-anchor="middle" class="label" font-weight="bold">{letter} · {name}</text>')
    use(letter,x,160,560)
    svg.append(f'<text x="{x}" y="367" text-anchor="middle" class="small">Enlarged silhouette</text>')
svg.append('<path d="M40 384H920" stroke="#bbc2bb"/>')
svg.append('<text x="40" y="417" class="label">At coding sizes</text>')
for row,size in enumerate([14,18,24,32,48]):
    top=450+row*40
    svg.append(f'<text x="40" y="{top+12}" class="small">{size} px</text>')
    for (letter,name,d),x in zip(paths,centers): use(letter,x,top,size)
svg.append('<rect x="40" y="684" width="880" height="164" rx="6" fill="#142130"/>')
svg.append('<text x="60" y="715" style="fill:#eeeddb;font-size:14px">Reversed · 18 / 24 / 32 px</text>')
for row,size in enumerate([18,24,32]):
    for (letter,name,d),x in zip(paths,centers): use(letter,x,736+row*30,size,'#eeeddb')
svg.append('<text x="40" y="878" class="small">Glyph-only prototypes · source apostrophe and working fonts unchanged · no candidate selected</text></svg>')
(OUT/f'{basename}.svg').write_text('\n'.join(svg))
(OUT/('horizontal-designs.json' if args.horizontal else 'kite-designs.json' if args.kite else 'designs.json')).write_text(json.dumps({'source':str(SOURCE.relative_to(ROOT)),'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'weight':350,'cell':600,'adopted':None,'candidates':[{ 'id':letter,'name':name,'bounds':list(path.bounds)} for letter,name,path in candidates]},indent=2)+'\n')
print(OUT/f'{basename}.svg')
