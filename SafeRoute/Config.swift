//
//  Config.swift
//  SafeRoute
//

import CoreLocation
import MapKit

/// Environment-level constants. Keep this the only place the backend URL lives.
nonisolated enum Config {
    /// Backend base URL (Xinyi's ngrok tunnel; it changes whenever ngrok restarts).
    /// If it contains "REPLACE-ME", RouteService uses `Mocks` instead of the network.
    static let baseURL = "https://prelaw-grandpa-front.ngrok-free.dev"

    /// True once `baseURL` points at a real backend.
    static var isBackendConfigured: Bool { !baseURL.contains("REPLACE-ME") }

    /// `min_risk` for GET /risk: cells below this are not fetched or drawn. Raise it if the heatmap is laggy.
    /// Measured against the server at 0.5: 1472 cells (0.67 MB) -> 836 smooth heat zones over 5 nested bands
    /// (48k points, 13 ms), where the old square heatmap drew 1215 merged rectangles. 10 bands (1516 zones) lagged. Lower thresholds fetch more:
    /// 0.3 -> 3266 cells (1.3 MB), 0.4 -> 2310, 0.6 -> 761.
    static let riskMinimum = 0.5

    /// UserDefaults key (via @AppStorage) for the remembered profile.
    static let profileStorageKey = "profile"

    /// UserDefaults key (via @AppStorage) for the remembered map style.
    static let mapStyleStorageKey = "mapStyle"

    /// UserDefaults key (via @AppStorage): true once the first-launch onboarding was completed.
    static let onboardingStorageKey = "hasCompletedOnboarding"

    /// UserDefaults keys (via @AppStorage) for the route options sent as `avoid`.
    static let avoidTollsStorageKey = "avoidTolls"
    static let avoidHighwaysStorageKey = "avoidHighways"

    /// `safety_weight` sent with every route request (0 = fastest, 1 = safest) until a slider exists.
    static let defaultSafetyWeight = 1.0

    /// Origin used when the user's location is unavailable: UT Austin, where the mock routes start.
    static let fallbackOrigin = CLLocationCoordinate2D(latitude: 30.2849, longitude: -97.7341)

    /// The backend's pilot area (`BOUNDS` in data/app.py). It answers 422 for points outside it, so the
    /// app checks first and shows a coverage message instead of a route.
    static let pilotLatitudes = 29.95...30.75
    static let pilotLongitudes = -98.1 ... -97.3

    static func isInPilotArea(_ coordinate: CLLocationCoordinate2D) -> Bool {
        pilotLatitudes.contains(coordinate.latitude) && pilotLongitudes.contains(coordinate.longitude)
    }

    /// Pilot area: downtown Austin, TX. Map fallback before location is available, and search bias.
    static let austinCenter = CLLocationCoordinate2D(latitude: 30.2672, longitude: -97.7431)
    static let austinRegion = MKCoordinateRegion(
        center: austinCenter,
        latitudinalMeters: 12_000,
        longitudinalMeters: 12_000
    )
}
