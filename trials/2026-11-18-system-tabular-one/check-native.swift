import Foundation
import CoreGraphics
import CoreText
let provider=CGDataProvider(url: URL(fileURLWithPath:CommandLine.arguments[1]) as CFURL)!
let base=CTFontCreateWithGraphicsFont(CGFont(provider)!,1000,nil,nil)
let descriptor=CTFontDescriptorCreateWithAttributes([kCTFontFeatureSettingsAttribute:[[kCTFontOpenTypeFeatureTag as String:"tnum",kCTFontOpenTypeFeatureValue as String:1]]] as CFDictionary)
let font=CTFontCreateCopyWithAttributes(base,1000,nil,descriptor)
let line=CTLineCreateWithAttributedString(NSAttributedString(string:"0123456789",attributes:[NSAttributedString.Key(kCTFontAttributeName as String):font]))
var glyphs:[CGGlyph]=[];var positions:[CGPoint]=[]
for run in CTLineGetGlyphRuns(line) as! [CTRun] {
 let n=CTRunGetGlyphCount(run);var gs=[CGGlyph](repeating:0,count:n);var ps=[CGPoint](repeating:.zero,count:n)
 CTRunGetGlyphs(run,CFRange(location:0,length:0),&gs);CTRunGetPositions(run,CFRange(location:0,length:0),&ps)
 glyphs += gs;positions += ps
}
precondition(glyphs.count==10 && glyphs[1]==CGGlyph(CommandLine.arguments[2])!,"Tabular 1 not selected")
for i in 0..<10 { precondition(abs(positions[i].x-Double(i)*630)<0.1,"Tabular advance changed") }
precondition(abs(CTLineGetTypographicBounds(line,nil,nil,nil)-6300)<0.1)
print("Native CoreText: System tabular 1 selected, all ten Book/Text digits have630-unit advances")
