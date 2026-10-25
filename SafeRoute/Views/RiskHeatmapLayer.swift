//
//  RiskHeatmapLayer.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// The crash-risk heatmap as its own `MapContent`. It takes only the precomputed bands, so a
/// route or profile change gives MapKit nothing new to evaluate here; all per-cell work (outlining,
/// smoothing) happened once when the grid loaded. Bands are nested and translucent, drawn lowest to
/// highest, so the overlap builds a gradient that is hottest in the middle; a wide faint stroke in the
/// band's own color feathers each outer edge.
struct RiskHeatmapLayer: MapContent {
    let bands: [HeatBand]
    /// Multiplier on the band colors' opacity; drive mode dims the heatmap so the route stays legible.
    var opacity: Double = 1

    /// Opacity of one band's fill; five stacked reach about 0.7 at the hottest spots.
    private static let bandOpacity = 0.22
    /// The feather stroke, in screen points. Coincident outlines of a hot cell stack their strokes into a glow.
    private static let edgeWidth: CGFloat = 10

    var body: some MapContent {
        ForEach(bands) { band in
            ForEach(band.zones) { zone in
                MapPolygon(Self.polygon(for: zone))
                    .foregroundStyle(Self.color(at: band.midpoint, opacity: opacity))
                    .stroke(Self.color(at: band.midpoint, opacity: opacity * 0.45), lineWidth: Self.edgeWidth)
            }
        }
    }

    /// Yellow at the low end of the drawn range through orange to red at risk 1.0, translucent.
    /// `t` is the band midpoint in 0...1.
    static func color(at t: Double, opacity: Double = 1) -> Color {
        let clamped = min(max(t, 0), 1)
        return Color(hue: (1 - clamped) * (60.0 / 360.0), saturation: 0.95, brightness: 1)
            .opacity(Self.bandOpacity * opacity)
    }

    private static func polygon(for zone: HeatZone) -> MKPolygon {
        let holes = zone.holes.map { MKPolygon(coordinates: $0, count: $0.count) }
        return MKPolygon(coordinates: zone.outer, count: zone.outer.count, interiorPolygons: holes.isEmpty ? nil : holes)
    }
}
