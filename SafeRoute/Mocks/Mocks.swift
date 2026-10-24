//
//  Mocks.swift
//  SafeRoute
//

import Foundation

/// Hardcoded backend responses so the UI is demoable without a server.
/// Stored as raw JSON so it goes through the same decoder as a real response.
nonisolated enum Mocks {
    /// POST /route for UT Austin (near DKR Stadium) -> downtown (Congress Ave & 5th St).
    ///
    /// - fastest: MLK Blvd east, merge onto I-35 southbound, exit to E 6th St, west to Congress.
    /// - safest:  San Jacinto Blvd south past the Capitol, Brazos St (one-way, low speed), 5th St to Congress.
    static let routeResponseJSON = Data("""
    {
      "fastest": {
        "polyline": [
          [30.2849, -97.7341], [30.2841, -97.7338], [30.2832, -97.7334], [30.2823, -97.7331],
          [30.2815, -97.7328], [30.2813, -97.7312], [30.2811, -97.7296], [30.2801, -97.7299],
          [30.2788, -97.7305], [30.2775, -97.7311], [30.2762, -97.7317], [30.2749, -97.7322],
          [30.2736, -97.7327], [30.2723, -97.7331], [30.2710, -97.7335], [30.2697, -97.7338],
          [30.2684, -97.7341], [30.2672, -97.7343], [30.2662, -97.7345], [30.2665, -97.7362],
          [30.2669, -97.7384], [30.2674, -97.7406], [30.2678, -97.7424], [30.2672, -97.7431]
        ],
        "minutes": 11.4,
        "miles": 2.6,
        "risk": 0.71
      },
      "safest": {
        "polyline": [
          [30.2849, -97.7341], [30.2847, -97.7352], [30.2838, -97.7357], [30.2828, -97.7360],
          [30.2818, -97.7362], [30.2810, -97.7364], [30.2801, -97.7367], [30.2792, -97.7370],
          [30.2784, -97.7373], [30.2775, -97.7376], [30.2766, -97.7379], [30.2756, -97.7382],
          [30.2745, -97.7385], [30.2744, -97.7396], [30.2732, -97.7400], [30.2719, -97.7404],
          [30.2706, -97.7408], [30.2693, -97.7412], [30.2680, -97.7416], [30.2668, -97.7420],
          [30.2670, -97.7428], [30.2672, -97.7431]
        ],
        "minutes": 14.9,
        "miles": 2.9,
        "risk": 0.44
      },
      "delta_minutes": 3.5,
      "risk_reduction_pct": 38,
      "hazards_avoided": ["2 unprotected left turns", "I-35 merge", "high-crash zone on E 6th St"]
    }
    """.utf8)
}
