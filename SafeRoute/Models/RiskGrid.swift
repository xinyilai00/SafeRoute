//
//  RiskGrid.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// GET /risk payload: a GeoJSON FeatureCollection of 200 m cells with `properties.risk` in 0...1.
/// Only the keys the app needs are decoded; everything else in the GeoJSON is ignored.
nonisolated struct RiskFeatureCollection: Decodable {
    let features: [RiskFeature]

    /// Drawable cells. GeoJSON coordinates are `[lng, lat]`; this flips them.
    var cells: [RiskCell] {
        var cells: [RiskCell] = []
        for feature in features {
            for ring in feature.geometry.outerRings {
                let coordinates = ring.compactMap { point -> CLLocationCoordinate2D? in
                    guard point.count >= 2 else { return nil }
                    return CLLocationCoordinate2D(latitude: point[1], longitude: point[0])
                }
                guard coordinates.count >= 3 else { continue }
                cells.append(RiskCell(id: cells.count, risk: feature.properties.risk, coordinates: coordinates))
            }
        }
        return cells
    }
}

nonisolated struct RiskFeature: Decodable {
    let properties: RiskProperties
    let geometry: RiskGeometry
}

nonisolated struct RiskProperties: Decodable {
    let risk: Double
}

/// Polygon or MultiPolygon geometry reduced to its outer rings (holes are dropped).
nonisolated struct RiskGeometry: Decodable {
    let type: String
    /// One outer ring per polygon, each a list of `[lng, lat]` points.
    let outerRings: [[[Double]]]

    private enum CodingKeys: String, CodingKey {
        case type, coordinates
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        switch type {
        case "Polygon":
            let rings = try container.decode([[[Double]]].self, forKey: .coordinates)
            outerRings = rings.first.map { [$0] } ?? []
        case "MultiPolygon":
            let polygons = try container.decode([[[[Double]]]].self, forKey: .coordinates)
            outerRings = polygons.compactMap(\.first)
        default:
            outerRings = []
        }
    }
}

/// One heatmap cell ready for `MapPolygon`.
nonisolated struct RiskCell: Identifiable {
    let id: Int
    /// 0...1, higher is riskier.
    let risk: Double
    let coordinates: [CLLocationCoordinate2D]
}
