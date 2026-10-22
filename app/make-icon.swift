// Erzeugt app/AppIcon.icns: abgerundetes Quadrat im Dunkel-Verlauf mit dem 🍺 aus der Oberfläche.
// Aufruf: swiftc app/make-icon.swift -o /tmp/make-icon && /tmp/make-icon app/AppIcon.icns
import Cocoa

func png(_ px: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4,
                               hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = CGFloat(px), inset = s * 0.098, box = NSRect(x: inset, y: inset, width: s - 2 * inset, height: s - 2 * inset)
    let shape = NSBezierPath(roundedRect: box, xRadius: box.width * 0.225, yRadius: box.width * 0.225)
    NSGradient(starting: NSColor(red: 0.20, green: 0.22, blue: 0.27, alpha: 1), ending: NSColor(red: 0.08, green: 0.09, blue: 0.12, alpha: 1))!
        .draw(in: shape, angle: -90)
    let f = NSFont(name: "AppleColorEmoji", size: box.width * 0.62)!
    let str = NSAttributedString(string: "🍺", attributes: [.font: f])
    let sz = str.size()
    str.draw(at: NSPoint(x: box.midX - sz.width / 2, y: box.midY - sz.height / 2))
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "AppIcon.icns"
let set = NSTemporaryDirectory() + "AppIcon.iconset"
try? FileManager.default.removeItem(atPath: set)
try! FileManager.default.createDirectory(atPath: set, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    try! png(base).write(to: URL(fileURLWithPath: "\(set)/icon_\(base)x\(base).png"))
    try! png(base * 2).write(to: URL(fileURLWithPath: "\(set)/icon_\(base)x\(base)@2x.png"))
}
let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
p.arguments = ["-c", "icns", set, "-o", out]; try! p.run(); p.waitUntilExit()
