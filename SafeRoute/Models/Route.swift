//
//  Route.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// One route from POST /route (`fastest` or `safest`). Field names follow the root CLAUDE.md contract.
nonisolated struct Route: Decodable, Equatable {
    /// `[lat, lng]` pairs, already in the order the app needs.
    let geometry: [[Double]]
    let etaMinutes: Double
    let distanceKm: Double
    /// Penalty points; lower is safer.
    let riskScore: Double
    let riskEvents: [RiskEvent]

    enum CodingKeys: String, CodingKey {
        case geometry
        case etaMinutes = "eta_minutes"
        case distanceKm = "distance_km"
        case riskScore = "risk_score"
        case riskEvents = "risk_events"
    }

    var coordinates: [CLLocationCoordinate2D] {
        geometry.compactMap { pair in
            guard pair.count >= 2 else { return nil }
            return CLLocationCoordinate2D(latitude: pair[0], longitude: pair[1])
        }
    }

    /// The app displays miles; the backend sends kilometers.
    var distanceMiles: Double { distanceKm * 0.621371 }
}

/// A hazard along a route.
nonisolated struct RiskEvent: Decodable, Equatable, Identifiable {
    /// Raw backend type string; use `kind` for a typed value.
    let type: String
    let lat: Double
    let lng: Double
    let description: String

    var id: String { "\(type)@\(lat),\(lng)" }
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: lat, longitude: lng) }
    var kind: RiskEventType { RiskEventType(rawValue: type) ?? .unknown }
}

/// Known `risk_events[].type` values. Unknown strings decode to `.unknown` so a backend addition never breaks the app.
nonisolated enum RiskEventType: String, CaseIterable {
    case leftTurn = "left_turn"
    case leftTurnMajor = "left_turn_major"
    case quickExitTurn = "quick_exit_turn"
    case highwayMerge = "highway_merge"
    case highCrashZone = "high_crash_zone"
    case unknown

    var displayName: String {
        switch self {
        case .leftTurn: "Left turn"
        case .leftTurnMajor: "Left turn across major road"
        case .quickExitTurn: "Quick exit turn"
        case .highwayMerge: "Highway merge"
        case .highCrashZone: "High-crash zone"
        case .unknown: "Hazard"
        }
    }

    var symbolName: String {
        switch self {
        case .leftTurn, .leftTurnMajor: "arrow.turn.up.left"
        case .quickExitTurn: "arrow.triangle.branch"
        case .highwayMerge: "arrow.triangle.merge"
        case .highCrashZone: "exclamationmark.triangle.fill"
        case .unknown: "exclamationmark.circle.fill"
        }
    }
}
