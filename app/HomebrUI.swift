// Natives Fenster für HomebrUI: startet den mitgelieferten Python-Server und zeigt ihn in einer WKWebView.
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKUIDelegate, WKNavigationDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var port = 8765
    var saveURL: URL?

    func applicationDidFinishLaunching(_ note: Notification) {
        port = pickPort()
        buildMenu()
        let cfg = WKWebViewConfiguration()
        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "HomebrUI"
        window.contentView = web
        window.delegate = self
        window.setFrameAutosaveName("HomebrUIMain")
        if !window.setFrameUsingName("HomebrUIMain") { window.center() }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        web.loadHTMLString(splashHTML(), baseURL: nil)
        startServer()
        waitForServer(tries: 100)
    }

    func config() -> [String: Any] {
        let f = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".brew-aufraeumer/config.json")
        if let d = try? Data(contentsOf: f), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] { return j }
        return [:]
    }
    func configuredPort() -> Int { config()["port"] as? Int ?? 8765 }

    /// Ladescreen im gespeicherten Farbschema (nutzt dieselben CSS-Variablen wie die Oberfläche).
    func splashHTML(_ message: String? = nil) -> String {
        let css = (try? String(contentsOf: Bundle.main.resourceURL!.appendingPathComponent("web/style.css"))) ?? ""
        var theme = config()["theme"] as? String ?? "auto"
        if theme.range(of: "^[a-z-]+$", options: .regularExpression) == nil { theme = "auto" }
        let body = message.map { "<p>\($0)</p>" } ?? "<div class=\"spin\"></div>"
        return """
        <!doctype html><html data-theme="\(theme)"><head><meta charset="utf-8"><style>\(css)
        html,body{height:100%;margin:0;display:block;background:var(--paper);color:var(--ink)}
        .splash{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;font:14px -apple-system,system-ui,sans-serif}
        .splash .beer{font-size:64px;line-height:1}.splash .word{font-size:26px;font-weight:600;letter-spacing:.2px}.splash b{color:var(--acc)}
        .spin{width:22px;height:22px;border:3px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:r .8s linear infinite}
        @keyframes r{to{transform:rotate(360deg)}}
        </style></head><body><div class="splash"><div class="beer">🍺</div><div class="word">Homebr<b>UI</b></div>\(body)</div></body></html>
        """
    }

    /// Standardport; ist er von etwas anderem als HomebrUI belegt, nimmt die App einen freien.
    func pickPort() -> Int {
        let p = configuredPort()
        if !portOpen(p) || isHomebrUI(p) { return p }
        let s = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(s) }
        var a = sockaddr_in()
        a.sin_family = sa_family_t(AF_INET); a.sin_addr.s_addr = inet_addr("127.0.0.1")  // Port 0: das System wählt
        _ = withUnsafePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(s, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(s, $0, &len) } }
        return Int(UInt16(bigEndian: a.sin_port))
    }

    func isHomebrUI(_ p: Int) -> Bool {
        var ok = false
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(p)/api/version")!, timeoutInterval: 1)
        req.setValue("1", forHTTPHeaderField: "X-BrewUI")
        URLSession.shared.dataTask(with: req) { d, _, _ in
            if let d = d, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], j["version"] != nil { ok = true }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 1.5)
        return ok
    }

    func startServer() {
        let res = Bundle.main.resourceURL!
        let py = res.appendingPathComponent("python/bin/python3")
        let p = Process()
        p.executableURL = py
        p.arguments = [res.appendingPathComponent("server.py").path, "--no-open"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PORT"] = String(port)
        // Finder startet Apps mit minimalem PATH; brew liegt je nach Chip in /opt/homebrew oder /usr/local
        env["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
        p.environment = env
        let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".brew-aufraeumer")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let log = dir.appendingPathComponent("server.log")
        FileManager.default.createFile(atPath: log.path, contents: nil)
        if let h = try? FileHandle(forWritingTo: log) { p.standardOutput = h; p.standardError = h }
        p.terminationHandler = { [weak self] _ in
            // Server beendet (z. B. Power-Button in der Oberfläche): App schließen, außer ein anderer Server hält den Port
            DispatchQueue.main.async { if self?.portOpen() == false { NSApp.terminate(nil) } }
        }
        do { try p.run(); server = p } catch {
            let a = NSAlert(); a.messageText = "HomebrUI"; a.informativeText = "Server konnte nicht gestartet werden: \(error.localizedDescription)"
            a.runModal(); NSApp.terminate(nil)
        }
    }

    func portOpen(_ p: Int? = nil) -> Bool {
        let s = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(s) }
        var a = sockaddr_in()
        a.sin_family = sa_family_t(AF_INET); a.sin_port = in_port_t(p ?? port).bigEndian
        a.sin_addr.s_addr = inet_addr("127.0.0.1")
        return withUnsafePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(s, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 } }
    }

    func waitForServer(tries: Int) {
        if portOpen() { web.load(URLRequest(url: URL(string: "http://127.0.0.1:\(port)/")!)); return }
        if tries <= 0 { web.loadHTMLString(splashHTML("Server startet nicht. Log: ~/.brew-aufraeumer/server.log"), baseURL: nil); return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.waitForServer(tries: tries - 1) }
    }

    // MARK: Menü (Edit-Menü nötig, damit Kopieren/Einfügen in der WebView geht)
    func buildMenu() {
        let main = NSMenu()
        func add(_ title: String, _ items: [(String, Selector?, String)]) {
            let item = NSMenuItem(); main.addItem(item)
            let m = NSMenu(title: title); item.submenu = m
            for (t, sel, key) in items {
                if t == "-" { m.addItem(.separator()) } else { m.addItem(NSMenuItem(title: t, action: sel, keyEquivalent: key)) }
            }
        }
        add("HomebrUI", [("HomebrUI beenden", #selector(NSApplication.terminate(_:)), "q")])
        add("Bearbeiten", [("Ausschneiden", #selector(NSText.cut(_:)), "x"), ("Kopieren", #selector(NSText.copy(_:)), "c"),
                           ("Einsetzen", #selector(NSText.paste(_:)), "v"), ("Alles auswählen", #selector(NSText.selectAll(_:)), "a")])
        add("Ansicht", [("Neu laden", #selector(reload), "r")])
        add("Fenster", [("Schließen", #selector(NSWindow.performClose(_:)), "w"), ("Minimieren", #selector(NSWindow.performMiniaturize(_:)), "m")])
        NSApp.mainMenu = main
    }
    @objc func reload() { web.reload() }

    // MARK: Lebenszyklus
    func windowWillClose(_ n: Notification) { NSApp.terminate(nil) }
    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ n: Notification) { server?.terminationHandler = nil; server?.terminate() }

    // MARK: WebView – confirm()/alert() und externe Links
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = m
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Abbrechen")
        done(a.runModal() == .alertFirstButtonReturn)
    }
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = m; a.runModal(); done()
    }
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if a.shouldPerformDownload { decisionHandler(.download); return }
        if let u = a.request.url, let h = u.host, h != "127.0.0.1", u.scheme == "http" || u.scheme == "https" {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }
    func webView(_ w: WKWebView, decidePolicyFor r: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(r.canShowMIMEType ? .allow : .download)
    }
    func webView(_ w: WKWebView, navigationAction: WKNavigationAction, didBecome d: WKDownload) { d.delegate = self }
    func webView(_ w: WKWebView, navigationResponse: WKNavigationResponse, didBecome d: WKDownload) { d.delegate = self }

    // MARK: Downloads (Brewfile-Export)
    func download(_ d: WKDownload, decideDestinationUsing r: URLResponse, suggestedFilename name: String, completionHandler done: @escaping (URL?) -> Void) {
        let p = NSSavePanel(); p.nameFieldStringValue = name
        if p.runModal() == .OK, let u = p.url { try? FileManager.default.removeItem(at: u); done(u) } else { done(nil) }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
