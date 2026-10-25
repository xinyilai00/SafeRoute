//
//  BootScreen.swift
//  SafeRoute
//

import SwiftUI

/// Cold-launch screen: the logo and wordmark centered on the icon's background color, held briefly,
/// then scaled up a touch while the whole screen fades to reveal the app underneath. About 2.1 s in all,
/// paced to feel calm rather than quick.
/// Everything behind it (the map, the risk grid fetch) is already running.
struct BootScreen: View {
    /// Called once the fade has finished and the screen can be removed.
    var onFinished: () -> Void

    @State private var scale: CGFloat = 1
    @State private var opacity: Double = 1

    /// Shown in full for this long before the fade starts.
    private static let holdSeconds = 1.5
    private static let fadeSeconds = 0.6

    var body: some View {
        ZStack {
            Brand.background
            VStack(spacing: 16) {
                Image(.safeRouteLogo)
                    .resizable()
                    .scaledToFit()
                    .frame(height: 150)
                // The logo has no text of its own.
                Text("SafeRoute")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .foregroundStyle(Brand.navy)
            }
            .scaleEffect(scale)
        }
        .ignoresSafeArea()
        .environment(\.colorScheme, .light)
        .opacity(opacity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("SafeRoute")
        .task {
            try? await Task.sleep(for: .seconds(Self.holdSeconds))
            withAnimation(.easeInOut(duration: Self.fadeSeconds)) {
                scale = 1.06
                opacity = 0
            }
            try? await Task.sleep(for: .seconds(Self.fadeSeconds))
            onFinished()
        }
    }
}

#Preview {
    BootScreen {}
}
