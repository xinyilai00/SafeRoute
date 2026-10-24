//
//  Mocks.swift
//  SafeRoute
//

import Foundation

/// Hardcoded backend responses so the UI is demoable without a server.
/// Stored as raw JSON (matching the contract in the root CLAUDE.md) so it goes through
/// the same decoder as a real response.
nonisolated enum Mocks {
    /// POST /route for UT Austin (near DKR Stadium) -> downtown (Congress Ave & 5th St).
    ///
    /// - fastest: left onto MLK Blvd, merge onto I-35 southbound, exit to E 6th St, left onto Congress.
    /// - safest:  San Jacinto Blvd south past the Capitol, Brazos St (one-way, low speed), 5th St to Congress.
    ///
    /// Every `risk_events` point is an actual vertex of its route's `geometry`.
    static let routeResponseJSON = Data("""
    {
      "fastest": {
        "geometry": [
          [30.2849, -97.7341], [30.2841, -97.7338], [30.2832, -97.7334], [30.2823, -97.7331],
          [30.2815, -97.7328], [30.2813, -97.7312], [30.2811, -97.7296], [30.2801, -97.7299],
          [30.2788, -97.7305], [30.2775, -97.7311], [30.2762, -97.7317], [30.2749, -97.7322],
          [30.2736, -97.7327], [30.2723, -97.7331], [30.2710, -97.7335], [30.2697, -97.7338],
          [30.2684, -97.7341], [30.2672, -97.7343], [30.2662, -97.7345], [30.2665, -97.7362],
          [30.2669, -97.7384], [30.2674, -97.7406], [30.2678, -97.7424], [30.2672, -97.7431]
        ],
        "eta_minutes": 9.8,
        "distance_km": 3.3,
        "risk_score": 14.0,
        "risk_events": [
          {"type": "left_turn_major", "lat": 30.2815, "lng": -97.7328, "description": "Left turn onto E Martin Luther King Jr Blvd"},
          {"type": "highway_merge", "lat": 30.2801, "lng": -97.7299, "description": "Merge onto I-35 southbound"},
          {"type": "left_turn_major", "lat": 30.2678, "lng": -97.7424, "description": "Left turn from E 6th St onto Congress Ave"}
        ]
      },
      "safest": {
        "geometry": [
          [30.2849, -97.7341], [30.2847, -97.7352], [30.2838, -97.7357], [30.2828, -97.7360],
          [30.2818, -97.7362], [30.2810, -97.7364], [30.2801, -97.7367], [30.2792, -97.7370],
          [30.2784, -97.7373], [30.2775, -97.7376], [30.2766, -97.7379], [30.2756, -97.7382],
          [30.2745, -97.7385], [30.2744, -97.7396], [30.2732, -97.7400], [30.2719, -97.7404],
          [30.2706, -97.7408], [30.2693, -97.7412], [30.2680, -97.7416], [30.2668, -97.7420],
          [30.2670, -97.7428], [30.2672, -97.7431]
        ],
        "eta_minutes": 13.1,
        "distance_km": 2.4,
        "risk_score": 8.7,
        "risk_events": [
          {"type": "left_turn", "lat": 30.2847, "lng": -97.7352, "description": "Left turn onto San Jacinto Blvd"},
          {"type": "left_turn", "lat": 30.2744, "lng": -97.7396, "description": "Left turn onto Brazos St"}
        ]
      },
      "comparison": {
        "minutes_added": 3.3,
        "risk_reduction_pct": 38,
        "summary": "+3 min, avoids the I-35 merge and 2 left turns across major roads"
      }
    }
    """.utf8)
}
