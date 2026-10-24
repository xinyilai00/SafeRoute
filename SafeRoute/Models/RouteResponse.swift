//
//  RouteResponse.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// `{"lat": ..., "lng": ...}` as used in the POST /route request. Note `lng`, not `lon`.
nonisolated struct Coordinate: Codable, Equatable {
    let lat: Double
    let lng: Double

    init(_ coordinate: CLLocationCoordinate2D) {
        lat = coordinate.latitude
        lng = coordinate.longitude
    }
}

/// POST /route request body.
nonisolated struct RouteRequest: Encodable {
    let origin: Coordinate
    let destination: Coordinate
    let profile: Profile
    /// 0 = fastest, 1 = safest. Fixed at 1.0 until a slider exists.
    let safetyWeight: Double

    enum CodingKeys: String, CodingKey {
        case origin, destination, profile
        case safetyWeight = "safety_weight"
    }
}

/// POST /route response body.
nonisolated struct RouteResponse: Decodable, Equatable {
    let fastest: Route
    let safest: Route
    let comparison: RouteComparison
}

nonisolated struct RouteComparison: Decodable, Equatable {
    let minutesAdded: Double
    let riskReductionPct: Double
    let summary: String

    enum CodingKeys: String, CodingKey {
        case minutesAdded = "minutes_added"
        case riskReductionPct = "risk_reduction_pct"
        case summary
    }
}
