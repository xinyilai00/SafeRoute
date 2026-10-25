//
//  MapStyleMenu.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// User-selectable base map. Stored by raw value with @AppStorage.
enum MapStyleChoice: String, CaseIterable, Identifiable {
    case standard
    case satellite
    case hybrid
    /// Standard map with muted colors so routes and the heatmap stand out.
    case muted

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .standard: "Standard"
        case .satellite: "Satellite"
        case .hybrid: "Hybrid"
        case .muted: "Muted"
        }
    }

    var symbolName: String {
        switch self {
        case .standard: "map"
        case .satellite: "globe.americas.fill"
        case .hybrid: "square.3.layers.3d"
        case .muted: "circle.lefthalf.filled"
        }
    }

    var mapStyle: MapStyle {
        switch self {
        case .standard: .standard
        case .satellite: .imagery
        case .hybrid: .hybrid
        case .muted: .standard(emphasis: .muted)
        }
    }
}

/// Circular glass button showing the current map style; opens a menu of the four styles.
struct MapStyleMenu: View {
    @Binding var selection: MapStyleChoice

    var body: some View {
        Menu {
            Picker("Map style", selection: $selection) {
                ForEach(MapStyleChoice.allCases) { choice in
                    Label(choice.displayName, systemImage: choice.symbolName)
                        .tag(choice)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: selection.symbolName)
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .contentTransition(.symbolEffect(.replace))
                .glassEffect(.regular.interactive(), in: .circle)
                .brandGlow(in: .circle)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .accessibilityLabel("Map style: \(selection.displayName)")
    }
}

#Preview {
    @Previewable @State var style: MapStyleChoice = .standard
    MapStyleMenu(selection: $style).padding()
}
