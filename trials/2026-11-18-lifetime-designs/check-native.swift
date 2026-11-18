import Foundation
import CoreGraphics
import CoreText
let path = CommandLine.arguments[1]
let ids = CommandLine.arguments[2].split(separator:",").map { CGGlyph($0)! }
let provider = CGDataProvider(url: URL(fileURLWithPath:path) as CFURL)!
let cgfont = CGFont(provider)!
let base = CTFontCreateWithGraphicsFont(cgfont,1000,nil,nil)
for enabled in [false,true] {
 let settings:[[String:Any]] = [[kCTFontOpenTypeFeatureTag as String:"calt",kCTFontOpenTypeFeatureValue as String:1], [kCTFontOpenTypeFeatureTag as String:"ss01",kCTFontOpenTypeFeatureValue as String:enabled ? 1 : 0]]
 let descriptor=CTFontDescriptorCreateWithAttributes([kCTFontFeatureSettingsAttribute:settings] as CFDictionary)
 let font=CTFontCreateCopyWithAttributes(base,1000,nil,descriptor)
 let line=CTLineCreateWithAttributedString(NSAttributedString(string:"&'a",attributes:[NSAttributedString.Key(kCTFontAttributeName as String):font,NSAttributedString.Key(kCTLigatureAttributeName as String):1]))
 let runs=CTLineGetGlyphRuns(line) as! [CTRun]
 var glyphs:[CGGlyph]=[];var positions:[CGPoint]=[]
 for run in runs {
  let count=CTRunGetGlyphCount(run)
  var gs=[CGGlyph](repeating:0,count:count);var ps=[CGPoint](repeating:.zero,count:count)
  CTRunGetGlyphs(run,CFRange(location:0,length:0),&gs);CTRunGetPositions(run,CFRange(location:0,length:0),&ps)
  glyphs += gs;positions += ps
 }
 precondition(glyphs.count==3 && glyphs[1]==ids[enabled ? 1 : 0],"Lifetime feature selection failed")
 precondition(abs(positions[0].x-(enabled ? 40 : 0))<0.1 && abs(positions[1].x-(enabled ? 640 : 600))<0.1 && abs(positions[2].x-1200)<0.1,"Cells shifted")
 precondition(abs(CTLineGetTypographicBounds(line,nil,nil,nil)-1800)<0.1,"Cell width changed")
 print("Native CoreText lifetime: ss01=\(enabled), marker selected, opt-in positioning and fixed advances verified")
}
