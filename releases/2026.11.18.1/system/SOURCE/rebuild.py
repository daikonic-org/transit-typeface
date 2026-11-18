from pathlib import Path
import gzip
from fontTools.ttLib import TTFont
r=Path(__file__).resolve().parent
f=TTFont(recalcTimestamp=False)
with gzip.open(next(r.glob('*.ttx.gz')), 'rb') as source:
    f.importXML(source)
f.save(r/'Rebuilt-VF.ttf')
