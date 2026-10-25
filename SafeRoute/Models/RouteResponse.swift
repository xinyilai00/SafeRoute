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
    /// Road types to steer clear of: any of `"highways"` and `"tolls"`. Empty = both allowed (the default).
    let avoid: [String]

    enum CodingKeys: String, CodingKey {
        case origin, destination, profile, avoid
        case safetyWeight = "safety_weight"
    }
}

/// POST /route response body.
nonisolated struct RouteResponse: Decodable, Equatable {
    let fastest: Route
    let safest: Route
    let comparison: RouteComparison

    /// The backend returns the same route twice when no alternative is meaningfully safer.
    var routesAreIdentical: Bool { fastest.geometry == safest.geometry }

    /// Hazard types the safest route has fewer of than the fastest, most avoided first.
    var avoidedHazards: [AvoidedHazard] {
        func counts(_ route: Route) -> [RiskEventType: Int] {
            route.riskEvents.reduce(into: [:]) { $0[$1.kind, default: 0] += 1 }
        }
        let fast = counts(fastest)
        let safe = counts(safest)
        return RiskEventType.allCases
            .compactMap { kind -> AvoidedHazard? in
                let difference = (fast[kind] ?? 0) - (safe[kind] ?? 0)
                return difference > 0 ? AvoidedHazard(kind: kind, count: difference) : nil
            }
            .sorted { $0.count > $1.count }
    }

    /// "Avoids 4 highway merges and 2 busy left turns." Nil when there is nothing to describe.
    var avoidanceSentence: String? {
        let items = avoidedHazards.map(\.text)
        switch items.count {
        case 0: return nil
        case 1: return "Avoids \(items[0])."
        case 2: return "Avoids \(items[0]) and \(items[1])."
        default: return "Avoids " + items.dropLast().joined(separator: ", ") + ", and \(items[items.count - 1])."
        }
    }
}

/// One hazard type the safe route has fewer of, with how many fewer.
nonisolated struct AvoidedHazard: Identifiable {
    let kind: RiskEventType
    let count: Int

    var id: String { kind.rawValue }
    var text: String { "\(count) \(kind.friendlyName(count: count))" }
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
