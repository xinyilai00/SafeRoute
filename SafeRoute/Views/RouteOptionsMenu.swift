//
//  RouteOptionsMenu.swift
//  SafeRoute
//

import SwiftUI

/// Circular glass button opening the route options: avoid tolls, avoid highways.
/// Both are remembered with @AppStorage by the caller; changing one re-requests the current route.
/// A small dot on the button shows when any option is on.
struct RouteOptionsMenu: View {
    @Binding var avoidTolls: Bool
    @Binding var avoidHighways: Bool

    private var isActive: Bool { avoidTolls || avoidHighways }

    var body: some View {
        Menu {
            Toggle("Avoid tolls", systemImage: "dollarsign.circle", isOn: $avoidTolls)
            Toggle("Avoid highways", systemImage: "road.lanes", isOn: $avoidHighways)
        } label: {
            Image(systemName: "slider.horizontal.3")
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .glassEffect(.regular.interactive(), in: .circle)
                .brandGlow(in: .circle)
                .overlay(alignment: .topTrailing) {
                    if isActive {
                        Circle()
                            .fill(.orange)
                            .frame(width: 10, height: 10)
                            .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
                            .offset(x: -4, y: 4)
                            .transition(.scale.combined(with: .opacity))
                    }
                }
                .animation(.snappy(duration: 0.2), value: isActive)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        switch (avoidTolls, avoidHighways) {
        case (true, true): "Route options: avoiding tolls and highways"
        case (true, false): "Route options: avoiding tolls"
        case (false, true): "Route options: avoiding highways"
        case (false, false): "Route options"
        }
    }
}

#Preview {
    @Previewable @State var tolls = true
    @Previewable @State var highways = false
    RouteOptionsMenu(avoidTolls: $tolls, avoidHighways: $highways).padding()
}
