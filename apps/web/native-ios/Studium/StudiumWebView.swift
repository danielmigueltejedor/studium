import SwiftUI
import UIKit
import WebKit

struct StudiumWebView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> StudiumViewController { StudiumViewController() }
    func updateUIViewController(_ controller: StudiumViewController, context: Context) {}
}

final class StudiumViewController: UIViewController, UIPencilInteractionDelegate {
    private let trustedHost = "studium-estudio-daniel.violetpark17.chatgpt.site"
    private let webView = WKWebView(frame: .zero)
    private var cloudBridge: StudiumCloudBridge?

    override func loadView() { view = webView }

    override func viewDidLoad() {
        super.viewDidLoad()
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.isInspectable = false
        let bridge = StudiumCloudBridge(presenter: self, webView: webView)
        cloudBridge = bridge
        webView.configuration.userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "studiumCloud")
        let interaction = UIPencilInteraction()
        interaction.delegate = self
        webView.addInteraction(interaction)
        if let url = URL(string: "https://\(trustedHost)/") {
            webView.load(URLRequest(url: url))
        }
    }

    @available(iOS 17.5, *)
    func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveTap tap: UIPencilInteraction.Tap) {
        dispatch(UIPencilInteraction.preferredTapAction, location: tap.hoverPose?.location)
    }

    @available(iOS 17.5, *)
    func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveSqueeze squeeze: UIPencilInteraction.Squeeze) {
        guard squeeze.phase == .ended else { return }
        dispatch(UIPencilInteraction.preferredSqueezeAction, location: squeeze.hoverPose?.location)
    }

    private func dispatch(_ preferred: UIPencilPreferredAction, location: CGPoint?) {
        guard let url = webView.url, url.scheme == "https", url.host == trustedHost,
              url.port == nil || url.port == 443 else { return }
        let action: String
        switch preferred {
        case .switchEraser, .switchPrevious: action = "toggle-eraser"
        case .showColorPalette, .showInkAttributes, .showContextualPalette: action = "palette"
        case .ignore, .runSystemShortcut: return
        @unknown default: return
        }
        var detail: [String: Any] = ["action": action]
        if let point = location { detail["x"] = point.x; detail["y"] = point.y }
        guard let data = try? JSONSerialization.data(withJSONObject: detail),
              let json = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('studium-pencil-action',{detail:\(json)}))")
    }
}
