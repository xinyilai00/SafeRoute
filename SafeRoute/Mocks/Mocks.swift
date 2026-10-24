//
//  Mocks.swift
//  SafeRoute
//

import Foundation

/// Hardcoded backend responses so the UI is demoable without a server.
/// Emitted as raw JSON (matching the contract in the root CLAUDE.md) so it goes through
/// the same decoder as a real response.
nonisolated enum Mocks {
    /// POST /route for UT Austin (near DKR Stadium) -> downtown (Congress Ave & 5th St).
    ///
    /// - fastest: left onto MLK Blvd, merge onto I-35 southbound, exit to E 6th St, left onto Congress.
    /// - safest:  San Jacinto Blvd south past the Capitol, Brazos St (one-way, low speed), 5th St to Congress.
    ///
    /// Geometry, ETA and distance are the same for every profile. Scores, hazards and the comparison vary
    /// so switching profiles is visibly different:
    /// - teen: the I-35 merge and the high-speed arterial.
    /// - elderly: unprotected left turns across major roads.
    /// - sensitive_passenger: rough pavement and sharp curves (described with existing event types).
    ///
    /// Every `risk_events` point is an actual vertex of its route's `geometry`.
    static func routeResponseJSON(for profile: Profile) -> Data {
        let v = variant(for: profile)
        return Data("""
        {
          "fastest": {
            "geometry": \(fastestGeometry),
            "eta_minutes": 9.8,
            "distance_km": 3.3,
            "risk_score": \(v.fastestRiskScore),
            "risk_events": \(events(v.fastestEvents))
          },
          "safest": {
            "geometry": \(safestGeometry),
            "eta_minutes": 13.1,
            "distance_km": 2.4,
            "risk_score": \(v.safestRiskScore),
            "risk_events": \(events(v.safestEvents))
          },
          "comparison": {
            "minutes_added": 3.3,
            "risk_reduction_pct": \(v.riskReductionPct),
            "summary": "\(v.summary)"
          }
        }
        """.utf8)
    }

    // MARK: - Per-profile content

    private struct Variant {
        let fastestRiskScore: Double
        let safestRiskScore: Double
        let riskReductionPct: Int
        let summary: String
        let fastestEvents: [Event]
        let safestEvents: [Event]
    }

    private struct Event {
        let type: String
        let lat: Double
        let lng: Double
        let description: String
    }

    // Vertices reused below (all appear in the geometry arrays).
    private static let mlkTurn = (30.2815, -97.7328)        // fastest: left onto MLK
    private static let i35Ramp = (30.2801, -97.7299)        // fastest: I-35 on-ramp
    private static let i35Downtown = (30.2749, -97.7322)    // fastest: I-35 through downtown
    private static let i35Lower = (30.2710, -97.7335)       // fastest: I-35 near 8th St
    private static let sixthExit = (30.2662, -97.7345)      // fastest: exit onto E 6th St
    private static let congressTurn = (30.2678, -97.7424)   // fastest: left onto Congress
    private static let sanJacintoTurn = (30.2847, -97.7352) // safest: left onto San Jacinto
    private static let brazosTurn = (30.2744, -97.7396)     // safest: left onto Brazos
    private static let sixthAndBrazos = (30.2680, -97.7416) // safest: E 6th & Brazos

    private static func variant(for profile: Profile) -> Variant {
        switch profile {
        case .teen:
            Variant(
                fastestRiskScore: 14.0,
                safestRiskScore: 8.7,
                riskReductionPct: 38,
                summary: "+3 min, avoids the I-35 merge and a high-speed arterial",
                fastestEvents: [
                    Event(type: "highway_merge", lat: i35Ramp.0, lng: i35Ramp.1,
                          description: "Merge onto I-35 southbound in fast traffic"),
                    Event(type: "high_crash_zone", lat: i35Downtown.0, lng: i35Downtown.1,
                          description: "High-speed stretch of I-35 through downtown"),
                    Event(type: "left_turn_major", lat: congressTurn.0, lng: congressTurn.1,
                          description: "Left turn from E 6th St onto Congress Ave"),
                ],
                safestEvents: [
                    Event(type: "left_turn", lat: sanJacintoTurn.0, lng: sanJacintoTurn.1,
                          description: "Left turn onto San Jacinto Blvd"),
                    Event(type: "left_turn", lat: brazosTurn.0, lng: brazosTurn.1,
                          description: "Left turn onto Brazos St"),
                ]
            )
        case .elderly:
            Variant(
                fastestRiskScore: 17.5,
                safestRiskScore: 8.9,
                riskReductionPct: 49,
                summary: "+3 min, avoids 2 unprotected left turns across major roads",
                fastestEvents: [
                    Event(type: "left_turn_major", lat: mlkTurn.0, lng: mlkTurn.1,
                          description: "Unprotected left turn across E Martin Luther King Jr Blvd"),
                    Event(type: "highway_merge", lat: i35Ramp.0, lng: i35Ramp.1,
                          description: "Merge onto I-35 southbound"),
                    Event(type: "left_turn_major", lat: congressTurn.0, lng: congressTurn.1,
                          description: "Unprotected left turn from E 6th St onto Congress Ave"),
                ],
                safestEvents: [
                    Event(type: "left_turn", lat: sanJacintoTurn.0, lng: sanJacintoTurn.1,
                          description: "Signal-protected left turn onto San Jacinto Blvd"),
                    Event(type: "left_turn", lat: brazosTurn.0, lng: brazosTurn.1,
                          description: "Left turn onto Brazos St (one-way, low speed)"),
                ]
            )
        case .sensitivePassenger:
            Variant(
                fastestRiskScore: 12.2,
                safestRiskScore: 6.1,
                riskReductionPct: 50,
                summary: "+3 min, avoids rough pavement and a sharp exit ramp",
                fastestEvents: [
                    Event(type: "highway_merge", lat: i35Ramp.0, lng: i35Ramp.1,
                          description: "Sharp curve on the I-35 on-ramp"),
                    Event(type: "high_crash_zone", lat: i35Lower.0, lng: i35Lower.1,
                          description: "Rough pavement on I-35 between 15th St and 7th St"),
                    Event(type: "quick_exit_turn", lat: sixthExit.0, lng: sixthExit.1,
                          description: "Tight exit ramp onto E 6th St"),
                ],
                safestEvents: [
                    Event(type: "left_turn", lat: brazosTurn.0, lng: brazosTurn.1,
                          description: "Left turn onto Brazos St"),
                    Event(type: "high_crash_zone", lat: sixthAndBrazos.0, lng: sixthAndBrazos.1,
                          description: "Uneven brick pavement at E 6th St & Brazos St"),
                ]
            )
        }
    }

    private static func events(_ events: [Event]) -> String {
        let items = events.map {
            """
            {"type": "\($0.type)", "lat": \($0.lat), "lng": \($0.lng), "description": "\($0.description)"}
            """
        }
        return "[\n      " + items.joined(separator: ",\n      ") + "\n    ]"
    }

    // MARK: - Geometry ([lat, lng] pairs)

    private static let fastestGeometry = """
    [
          [30.2849, -97.7341], [30.2841, -97.7338], [30.2832, -97.7334], [30.2823, -97.7331],
          [30.2815, -97.7328], [30.2813, -97.7312], [30.2811, -97.7296], [30.2801, -97.7299],
          [30.2788, -97.7305], [30.2775, -97.7311], [30.2762, -97.7317], [30.2749, -97.7322],
          [30.2736, -97.7327], [30.2723, -97.7331], [30.2710, -97.7335], [30.2697, -97.7338],
          [30.2684, -97.7341], [30.2672, -97.7343], [30.2662, -97.7345], [30.2665, -97.7362],
          [30.2669, -97.7384], [30.2674, -97.7406], [30.2678, -97.7424], [30.2672, -97.7431]
        ]
    """

    private static let safestGeometry = """
    [
          [30.2849, -97.7341], [30.2847, -97.7352], [30.2838, -97.7357], [30.2828, -97.7360],
          [30.2818, -97.7362], [30.2810, -97.7364], [30.2801, -97.7367], [30.2792, -97.7370],
          [30.2784, -97.7373], [30.2775, -97.7376], [30.2766, -97.7379], [30.2756, -97.7382],
          [30.2745, -97.7385], [30.2744, -97.7396], [30.2732, -97.7400], [30.2719, -97.7404],
          [30.2706, -97.7408], [30.2693, -97.7412], [30.2680, -97.7416], [30.2668, -97.7420],
          [30.2670, -97.7428], [30.2672, -97.7431]
        ]
    """
}
