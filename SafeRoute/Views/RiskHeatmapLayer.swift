//
//  RiskHeatmapLayer.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// The crash-risk heatmap as its own `MapContent`. It takes only the precomputed bands, so a
/// route or profile change gives MapKit nothing new to evaluate here; all per-cell work (banding,
/// merging, colors) happened once when the grid loaded.
struct RiskHeatmapLayer: MapContent {
    let bands: [HeatBand]
    /// Multiplier on the band colors' opacity; drive mode dims the heatmap so the route stays legible.
    var opacity: Double = 1

    var body: some MapContent {
        ForEach(bands) { band in
            ForEach(band.polygons) { polygon in
                MapPolygon(coordinates: polygon.coordinates)
                    .stroke(.clear, lineWidth: 0)
            }
            .foregroundStyle(Self.color(at: band.midpoint, opacity: opacity))
        }
    }

    /// Yellow at the low end of the drawn range through orange to red at risk 1.0, semi-transparent.
    /// `t` is the band midpoint in 0...1.
    static func color(at t: Double, opacity: Double = 1) -> Color {
        let clamped = min(max(t, 0), 1)
        return Color(hue: (1 - clamped) * (60.0 / 360.0), saturation: 0.95, brightness: 1)
            .opacity((0.3 + 0.3 * clamped) * opacity)
    }
}
