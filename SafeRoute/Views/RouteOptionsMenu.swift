//
//  RouteOptionsMenu.swift
//  SafeRoute
//

import SwiftUI

/// Which road types the route may use. Both are on by default: highways and toll roads often save
/// real time. Turning one off sends it to the backend as `avoid` (a strong preference, not a ban).
struct RouteOptionsMenu: View {
    @Binding var allowsHighways: Bool
    @Binding var allowsTolls: Bool

    /// True when the driver has turned something off, so the button can show it's not the default.
    private var isCustomized: Bool { !allowsHighways || !allowsTolls }

    var body: some View {
        Menu {
            Section("Route may use") {
                Toggle(isOn: $allowsHighways) {
                    Label("Highways", systemImage: "road.lanes")
                }
                Toggle(isOn: $allowsTolls) {
                    Label("Toll roads", systemImage: "dollarsign.circle")
                }
            }
        } label: {
            Image(systemName: "slider.horizontal.3")
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .glassEffect(.regular.interactive(), in: .circle)
                .overlay(alignment: .topTrailing) {
                    if isCustomized {
                        Circle()
                            .fill(.orange)
                            .frame(width: 11, height: 11)
                            .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
                            .offset(x: -3, y: 3)
                    }
                }
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .accessibilityLabel("Route options")
        .accessibilityValue(summary)
    }

    private var summary: String {
        switch (allowsHighways, allowsTolls) {
        case (true, true): "Highways and toll roads allowed"
        case (false, true): "Avoiding highways"
        case (true, false): "Avoiding toll roads"
        case (false, false): "Avoiding highways and toll roads"
        }
    }
}

#Preview {
    @Previewable @State var highways = true
    @Previewable @State var tolls = true
    RouteOptionsMenu(allowsHighways: $highways, allowsTolls: $tolls).padding()
}
