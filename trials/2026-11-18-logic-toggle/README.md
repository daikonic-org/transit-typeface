# Logic toggle

Stylistic set ss02 is labeled Logic in the font. It controls all six enclosure ligatures: <> diamond, [] box, <[ / ]> and [< / >] compound pairs. It is off by default. Enable ss02=1 (HarfBuzz/WezTerm) or "ss02" 1 (CSS font-feature-settings), or choose Logic from the application stylistic-set menu. Other coding ligatures remain under calt; compact lifetime placement remains independently controlled by ss01.

Logic on/off is tested with calt and ss01 each on/off: all8feature combinations at11weights. The enclosure forms retain1200-unit advances,600-unit carets, existing delimiter weight/height and nesting behavior. Arrows, comparisons, scope/access pairs, lifetimes and pipe forms are unchanged by the Logic toggle. Default-off shaping and the actual feature UI label are verified; OTS passed. Matched SVG/PNG/PDF shows Logic on/off with calt enabled on both sides.

Installable1.032preview has VF and3namedTTFs. This local preview is not installed or published;1.027remains installed/current.
