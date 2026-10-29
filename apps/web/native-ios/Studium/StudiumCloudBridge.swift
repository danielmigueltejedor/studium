import Foundation
import UIKit
import UniformTypeIdentifiers
import WebKit
import CryptoKit

final class StudiumCloudBridge: NSObject, WKScriptMessageHandlerWithReply, UIDocumentPickerDelegate, NSFilePresenter, URLSessionTaskDelegate {
    private let trustedHost = "studium-estudio-daniel.violetpark17.chatgpt.site"
    private let bookmarkPrefix = "studium.cloud.folder."
    private var activeScope: String?
    private var pickerScope: String?
    private var authCache: [String: (scope: String, expires: Date)] = [:]
    private weak var presenter: UIViewController?
    private weak var webView: WKWebView?
    private let ioQueue = DispatchQueue(label: "studium.cloud.io", qos: .utility)
    private let fileQueue = OperationQueue()
    private var folder: URL?
    private var registeredPresenter = false
    private var pickerReply: ((Any?, String?) -> Void)?
    private var observers: [NSObjectProtocol] = []

    var presentedItemURL: URL? { folder }
    var presentedItemOperationQueue: OperationQueue { fileQueue }

    init(presenter: UIViewController, webView: WKWebView) {
        self.presenter = presenter
        self.webView = webView
        super.init()
        fileQueue.maxConcurrentOperationCount = 1
        registerPresenter()
        observers.append(NotificationCenter.default.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { [weak self] _ in self?.unregisterPresenter() })
        observers.append(NotificationCenter.default.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil, queue: .main) { [weak self] _ in self?.registerPresenter(); self?.notifyChange() })
    }

    deinit {
        unregisterPresenter()
        for observer in observers { NotificationCenter.default.removeObserver(observer) }
    }

    private func trusted(_ message: WKScriptMessage? = nil) -> Bool {
        guard let view = webView, let current = view.url, current.scheme == "https", current.host == trustedHost,
              current.port == nil || current.port == 443 else { return false }
        guard let message else { return true }
        let origin = message.frameInfo.securityOrigin
        guard message.webView === view, message.frameInfo.isMainFrame, origin.protocol == "https", origin.host == trustedHost,
              origin.port == 0 || origin.port == 443, let source = message.frameInfo.request.url,
              source.scheme == "https", source.host == trustedHost, source.port == nil || source.port == 443 else { return false }
        return true
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard trusted(message), let body = message.body as? [String: Any], let operation = body["operation"] as? String else {
            replyHandler(nil, "Origen no autorizado."); return
        }
        guard let requestedScope = body["scope"] as? String, UUID(uuidString: requestedScope) != nil else {
            replyHandler(nil, "Entra en tu cuenta Studium antes de conectar la carpeta."); return
        }
        verifyAccount(scope: requestedScope) { [weak self] allowed in
            guard let self, allowed, self.trusted(message) else { replyHandler(nil, "No se pudo comprobar la cuenta de esta sesión."); return }
            self.activateScope(requestedScope)
            self.handle(operation, body: body, replyHandler: replyHandler)
        }
    }

    private func handle(_ operation: String, body: [String: Any], replyHandler: @escaping (Any?, String?) -> Void) {
        if operation == "choose" {
            guard pickerReply == nil, let presenter else { replyHandler(nil, "Termina primero la selección de carpeta."); return }
            pickerReply = replyHandler
            pickerScope = activeScope
            let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder], asCopy: false)
            picker.allowsMultipleSelection = false
            picker.delegate = self
            presenter.present(picker, animated: true)
            return
        }
        if operation == "status" { replyHandler(["available": true, "connected": folder != nil], nil); return }
        if operation == "disconnect" {
            unregisterPresenter(); folder = nil
            if let activeScope { UserDefaults.standard.removeObject(forKey: bookmarkPrefix + activeScope) }
            replyHandler(["disconnected": true], nil); return
        }
        guard ["get", "put"].contains(operation), let scope = body["scope"] as? String, UUID(uuidString: scope) != nil,
              let kind = body["kind"] as? String, ["manifest", "object"].contains(kind) else {
            replyHandler(nil, "Operación de nube no válida."); return
        }
        let hash = body["hash"] as? String ?? ""
        if kind == "object", hash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) == nil {
            replyHandler(nil, "Identificador de archivo no válido."); return
        }
        let selectedFolder = folder
        ioQueue.async { [weak self] in
            guard let self, let selectedFolder, selectedFolder.startAccessingSecurityScopedResource() else {
                DispatchQueue.main.async { replyHandler(nil, "Vuelve a elegir la carpeta en Archivos para recuperar el permiso.") }; return
            }
            defer { selectedFolder.stopAccessingSecurityScopedResource() }
            do {
                let accountDirectory = selectedFolder.appendingPathComponent("Studium", isDirectory: true).appendingPathComponent(scope, isDirectory: true)
                let file = kind == "manifest" ? accountDirectory.appendingPathComponent("manifest.json") : accountDirectory.appendingPathComponent("objects", isDirectory: true).appendingPathComponent(hash + ".bin")
                let result: [String: Any]
                if operation == "get" { result = try self.read(file) }
                else {
                    guard let encoded = body["data"] as? String, encoded.utf8.count <= 12 * 1024 * 1024,
                          let bytes = Data(base64Encoded: encoded), bytes.count <= 8 * 1024 * 1024 else { throw CloudFailure.invalidData }
                    if kind == "object", self.digest(bytes) != hash { throw CloudFailure.invalidData }
                    try self.createDirectories(file.deletingLastPathComponent(), inside: selectedFolder)
                    result = try self.write(file, bytes: bytes, expected: body["expectedETag"] as? String, immutable: kind == "object")
                }
                DispatchQueue.main.async { replyHandler(result, nil) }
            } catch {
                let message: String
                switch error {
                case CloudFailure.conflict: message = "Hay cambios de otro dispositivo. Ambas versiones se conservan; revisa el conflicto antes de sustituirlas."
                case CloudFailure.invalidData: message = "El archivo no coincide con el formato o la huella esperados."
                default: message = "No se pudo leer o guardar en la carpeta. Comprueba iCloud en Archivos y vuelve a elegir la carpeta si hace falta."
                }
                DispatchQueue.main.async { replyHandler(nil, message) }
            }
        }
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard trusted(), let selected = urls.first, selected.startAccessingSecurityScopedResource() else {
            pickerReply?(nil, "No se pudo abrir la carpeta elegida."); pickerReply = nil; return
        }
        defer { selected.stopAccessingSecurityScopedResource() }
        do {
            let bookmark = try selected.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil)
            guard let pickerScope, pickerScope == activeScope else { throw CloudFailure.coordination }
            unregisterPresenter(); folder = selected
            UserDefaults.standard.set(bookmark, forKey: bookmarkPrefix + pickerScope)
            registerPresenter()
            pickerReply?(["connected": true], nil)
        } catch { pickerReply?(nil, "No se pudo conservar el permiso de la carpeta.") }
        pickerReply = nil
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        pickerReply?(nil, "Selección de carpeta cancelada."); pickerReply = nil
    }

    private func activateScope(_ scope: String) {
        guard scope != activeScope else { return }
        unregisterPresenter(); folder = nil; activeScope = scope
        if let data = UserDefaults.standard.data(forKey: bookmarkPrefix + scope) {
            var stale = false
            if let restored = try? URL(resolvingBookmarkData: data, options: [], relativeTo: nil, bookmarkDataIsStale: &stale), !stale { folder = restored }
        }
        registerPresenter()
    }

    private func verifyAccount(scope: String, completion: @escaping (Bool) -> Void) {
        guard let webView else { completion(false); return }
        webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { [weak self] cookies in
            guard let self, let cookie = cookies.first(where: { $0.name == "__Host-studium-session" && $0.domain == self.trustedHost }),
                  let expiry = cookie.expiresDate, expiry > Date() else { completion(false); return }
            let tokenHash = self.digest(Data(cookie.value.utf8))
            if let cached = self.authCache[tokenHash], cached.scope == scope, cached.expires > Date() { completion(true); return }
            var request = URLRequest(url: URL(string: "https://\(self.trustedHost)/api/account/me")!)
            request.timeoutInterval = 20
            request.setValue("__Host-studium-session=" + cookie.value, forHTTPHeaderField: "Cookie")
            let session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
            session.dataTask(with: request) { [weak self] data, response, error in
                defer { session.finishTasksAndInvalidate() }
                guard let self else { DispatchQueue.main.async { completion(false) }; return }
                var json: [String: Any]?
                if let data, data.count < 32768 { json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] }
                let user = json?["user"] as? [String: Any]
                let valid = (response as? HTTPURLResponse)?.statusCode == 200 && user?["id"] as? String == scope
                DispatchQueue.main.async {
                    if valid {
                        self.authCache[tokenHash] = (scope, Date().addingTimeInterval(300))
                        UserDefaults.standard.set(["scope": scope, "expires": expiry.timeIntervalSince1970], forKey: "studium.cloud.auth." + tokenHash)
                        completion(true)
                    } else if error != nil,
                              let previous = UserDefaults.standard.dictionary(forKey: "studium.cloud.auth." + tokenHash),
                              previous["scope"] as? String == scope,
                              let until = previous["expires"] as? Double, until > Date().timeIntervalSince1970 {
                        completion(true)
                    } else { completion(false) }
                }
            }.resume()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }

    private func createDirectories(_ target: URL, inside root: URL) throws {
        var coordinationError: NSError?
        var operationError: Error?
        var ran = false
        NSFileCoordinator(filePresenter: nil).coordinate(writingItemAt: root, options: [], error: &coordinationError) { coordinatedRoot in
            ran = true
            do { let relative = target.path.dropFirst(root.path.count).split(separator: "/").map(String.init)
                let coordinatedTarget = relative.reduce(coordinatedRoot) { $0.appendingPathComponent($1, isDirectory: true) }
                try FileManager.default.createDirectory(at: coordinatedTarget, withIntermediateDirectories: true) }
            catch { operationError = error }
        }
        if let error = coordinationError { throw error }
        if let error = operationError { throw error }
        if !ran { throw CloudFailure.coordination }
    }

    private func read(_ file: URL) throws -> [String: Any] {
        var coordinationError: NSError?
        var operationError: Error?
        var result: [String: Any]?
        NSFileCoordinator(filePresenter: nil).coordinate(readingItemAt: file, options: [], error: &coordinationError) { coordinated in
            do {
                let data = try self.boundedData(coordinated)
                if data.count > 8 * 1024 * 1024 { throw CloudFailure.invalidData }
                let conflicts = NSFileVersion.unresolvedConflictVersionsOfItem(at: coordinated) ?? []
                result = ["found": true, "data": data.base64EncodedString(), "etag": self.digest(data), "hasConflicts": !conflicts.isEmpty]
            } catch let error as CocoaError where error.code == .fileReadNoSuchFile { result = ["found": false] }
            catch { operationError = error }
        }
        if let error = coordinationError {
            if error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError { return ["found": false] }
            throw error
        }
        if let error = operationError { throw error }
        guard let result else { throw CloudFailure.coordination }
        return result
    }

    private func write(_ file: URL, bytes: Data, expected: String?, immutable: Bool) throws -> [String: Any] {
        var coordinationError: NSError?
        var operationError: Error?
        var result: [String: Any]?
        NSFileCoordinator(filePresenter: nil).coordinate(writingItemAt: file, options: [.forReplacing], error: &coordinationError) { coordinated in
            do {
                if let versions = NSFileVersion.unresolvedConflictVersionsOfItem(at: coordinated), !versions.isEmpty { throw CloudFailure.conflict }
                if FileManager.default.fileExists(atPath: coordinated.path) {
                    let current = try self.boundedData(coordinated)
                    if immutable {
                        if self.digest(current) != self.digest(bytes) { throw CloudFailure.invalidData }
                        result = ["savedLocally": true, "etag": self.digest(current)]; return
                    }
                    if expected != self.digest(current) { throw CloudFailure.conflict }
                } else if let expected, !expected.isEmpty { throw CloudFailure.conflict }
                try bytes.write(to: coordinated, options: .atomic)
                let resources = try? coordinated.resourceValues(forKeys: [.isUbiquitousItemKey, .ubiquitousItemIsUploadedKey, .ubiquitousItemIsUploadingKey])
                result = ["savedLocally": true, "etag": self.digest(bytes), "isICloud": resources?.isUbiquitousItem ?? false,
                          "uploadConfirmed": resources?.ubiquitousItemIsUploaded ?? false,
                          "uploading": resources?.ubiquitousItemIsUploading ?? false]
            } catch { operationError = error }
        }
        if let error = coordinationError { throw error }
        if let error = operationError { throw error }
        guard let result else { throw CloudFailure.coordination }
        return result
    }

    private func boundedData(_ url: URL) throws -> Data {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var result = Data()
        while let part = try handle.read(upToCount: 1024 * 1024), !part.isEmpty {
            if result.count + part.count > 8 * 1024 * 1024 { throw CloudFailure.invalidData }
            result.append(part)
        }
        return result
    }

    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func registerPresenter() { if folder != nil && !registeredPresenter { NSFileCoordinator.addFilePresenter(self); registeredPresenter = true } }
    private func unregisterPresenter() { if registeredPresenter { NSFileCoordinator.removeFilePresenter(self); registeredPresenter = false } }
    func presentedItemDidChange() { notifyChange() }
    func presentedSubitemDidChange(at url: URL) { notifyChange() }
    func presentedSubitem(at url: URL, didGain version: NSFileVersion) { notifyChange() }
    private func notifyChange() {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.trusted() else { return }
            self.webView?.evaluateJavaScript("window.dispatchEvent(new Event('studium-cloud-change'))")
        }
    }
    private enum CloudFailure: Error { case conflict, invalidData, coordination }
}
