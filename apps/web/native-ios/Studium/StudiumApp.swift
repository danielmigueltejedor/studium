import SwiftUI

@main
struct StudiumApp: App {
    var body: some Scene {
        WindowGroup { StudiumWebView().ignoresSafeArea(edges: .bottom) }
    }
}
