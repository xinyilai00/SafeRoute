//
//  RiskGrid.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// GET /risk response: a GeoJSON FeatureCollection of polygons, each with `properties.risk` in 0...1.
nonisolated struct RiskGridResponse: Decodable {
    let features: [Feature]

    struct Feature: Decodable {
        let geometry: Geometry
        let properties: Properties
    }

    struct Geometry: Decodable {
        /// Polygon rings of `[lng, lat]` pairs (standard GeoJSON order).
        let coordinates: [[[Double]]]
    }

    struct Properties: Decodable {
        let risk: Double
    }
}

/// One heatmap cell, ready to draw.
nonisolated struct RiskCell: Identifiable, Equatable {
    let id: Int
    /// Outer ring as map coordinates (GeoJSON `[lng, lat]` flipped to latitude/longitude).
    let ring: [CLLocationCoordinate2D]
    let risk: Double

    static func == (lhs: RiskCell, rhs: RiskCell) -> Bool { lhs.id == rhs.id && lhs.risk == rhs.risk }

    static func cells(from response: RiskGridResponse) -> [RiskCell] {
        response.features.enumerated().compactMap { index, feature in
            guard let outer = feature.geometry.coordinates.first else { return nil }
            let ring = outer.compactMap { pair -> CLLocationCoordinate2D? in
                guard pair.count >= 2 else { return nil }
                return CLLocationCoordinate2D(latitude: pair[1], longitude: pair[0])
            }
            guard ring.count >= 3 else { return nil }
            return RiskCell(id: index, ring: ring, risk: feature.properties.risk)
        }
    }
}
