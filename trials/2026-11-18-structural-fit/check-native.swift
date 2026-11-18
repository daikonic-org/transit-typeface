import Foundation
import CoreGraphics
import CoreText
let args=CommandLine.arguments
let provider=CGDataProvider(url:URL(fileURLWithPath:args[1]) as CFURL)!
let base=CTFontCreateWithGraphicsFont(CGFont(provider)!,1000,nil,nil)
let mixed=args[2].split(separator:",").map{CGGlyph($0)!}
let close=CGGlyph(args[3])!
for logic in [false,true] {
 let settings:[[String:Any]]=[[kCTFontOpenTypeFeatureTag as String:"calt",kCTFontOpenTypeFeatureValue as String:1],[kCTFontOpenTypeFeatureTag as String:"ss02",kCTFontOpenTypeFeatureValue as String:logic ? 1 : 0]]
 let descriptor=CTFontDescriptorCreateWithAttributes([kCTFontFeatureSettingsAttribute:settings] as CFDictionary)
 let font=CTFontCreateCopyWithAttributes(base,1000,nil,descriptor)
 for text in ["<[T]>","Vec<Vec<T>>","a >> b"] {
  let line=CTLineCreateWithAttributedString(NSAttributedString(string:text,attributes:[NSAttributedString.Key(kCTFontAttributeName as String):font,NSAttributedString.Key(kCTLigatureAttributeName as String):1]))
  var gs:[CGGlyph]=[];var ps:[CGPoint]=[]
  for run in CTLineGetGlyphRuns(line) as! [CTRun] {
   let n=CTRunGetGlyphCount(run);var glyphs=[CGGlyph](repeating:0,count:n);var points=[CGPoint](repeating:.zero,count:n)
   CTRunGetGlyphs(run,CFRange(location:0,length:0),&glyphs);CTRunGetPositions(run,CFRange(location:0,length:0),&points)
   gs += glyphs;ps += points
  }
  precondition(abs(CTLineGetTypographicBounds(line,nil,nil,nil)-Double(text.count)*600)<0.1,"Cell widths changed")
  if text=="<[T]>" {
   precondition(gs==mixed,"Mixed enclosures must stay separate")
   for (i,x) in [30.0,570,1200,1830,2370].enumerated(){precondition(abs(ps[i].x-x)<0.1,"Mixed fit applied incorrectly")}
  } else if text=="Vec<Vec<T>>" {precondition(gs.last==close,"Nested closers not fitted")}
  else {precondition(!gs.contains(close),"Shift operator changed")}
 }
 print("Native CoreText Logic=\(logic): separate mixed glyphs, single60-unit tightening, nested closers and fixed cells verified")
}
