//
//  Atmosphere.swift
//  SafeRoute
//

import SwiftUI
import UIKit

/// Stretches its content to the physical screen edges. Overlays on the `Map` stop at the device's own
/// safe-area insets (the map consumes those before its overlays see them, so `ignoresSafeArea` there only
/// recovers the insets the search reserve and the card add); this measures the remaining gap to the window
/// edges and extends the content by exactly that much, top and bottom.
struct ScreenEdges<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        GeometryReader { geo in
            let frame = geo.frame(in: .global)
            let topGap = max(0, frame.minY)
            let bottomGap = max(0, Self.windowHeight - frame.maxY)
            content()
                .padding(.top, -topGap)
                .padding(.bottom, -bottomGap)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    private static var windowHeight: CGFloat {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        return scene?.screen.bounds.height ?? 0
    }
}

/// Soft, colorless blur fading down from the physical top edge of the screen, so the status bar and the
/// search field sit on a calm band instead of raw map detail, like the top of most iOS apps. Drawn over
/// the map, under the search bar. The thinnest system material is used because no public API gives a
/// blur with no tint at all; the mask keeps it faint.
struct TopEdgeBlur: View {
    var body: some View {
        Rectangle()
            .fill(.ultraThinMaterial)
            .mask {
                LinearGradient(
                    stops: [
                        .init(color: .black.opacity(0.9), location: 0),
                        .init(color: .black.opacity(0.55), location: 0.45),
                        .init(color: .clear, location: 1),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            }
            .frame(height: 160)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

/// The onboarding background's wash of sky blue and sunset coral, rising from the physical bottom edge.
/// Sits over the map and under the route card, which picks the colors up through its glass. Driven by a
/// clock rather than a state animation (which would not start reliably on a view inserted with a
/// transition): each blob wanders slowly on its own cycle and leans toward a neighbouring brand color and
/// back, so the glow feels alive without drawing the eye.
struct BottomGlow: View {
    private static let start = Date()

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 24)) { context in
            let t = context.date.timeIntervalSince(Self.start)
            ZStack {
                blob(Brand.skyBlue, toward: Brand.coral, size: 380, at: (-130, 130), t: t, period: 11, phase: 0)
                blob(Brand.coral, toward: Brand.skyBlue, size: 360, at: (140, 150), t: t, period: 15, phase: 2.1)
                blob(Brand.background, toward: Brand.coral, size: 320, at: (0, 200), t: t, period: 19, phase: 4.2)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: 440)
        .mask {
            LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// One cycle of `period` seconds moves the blob about 70 pt sideways and 26 pt up and down; the color
    /// leans up to 60% toward the other color on a slightly slower cycle so motion and hue never line up.
    private func blob(_ base: Color, toward other: Color, size: CGFloat, at origin: (x: CGFloat, y: CGFloat),
                      t: Double, period: Double, phase: Double) -> some View {
        let w = 2 * .pi * t / period + phase
        let lean = 0.6 * 0.5 * (1 + sin(w * 0.8))
        return Circle()
            .fill(base.mix(with: other, by: lean).opacity(0.65))
            .frame(width: size, height: size)
            .blur(radius: 70)
            .offset(x: origin.x + 70 * sin(w), y: origin.y + 26 * cos(w * 0.7))
    }
}

extension View {
    /// A soft wash of the logo's sky blue and sunset coral behind and just around a glass control, so the
    /// glass picks up some color and reads lighter and less opaque over a busy map. Apply after `.glassEffect`.
    func brandGlow<S: Shape>(in shape: S) -> some View {
        background {
            shape
                .fill(
                    LinearGradient(
                        colors: [Brand.skyBlue.opacity(0.6), Brand.coral.opacity(0.6)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .padding(-1)
                .blur(radius: 4)
        }
        .shadow(color: Brand.skyBlue.opacity(0.18), radius: 6, y: 2)
    }
}
