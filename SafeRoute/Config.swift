//
//  Config.swift
//  SafeRoute
//

import CoreLocation
import MapKit

/// Environment-level constants. Keep this the only place the backend URL lives.
nonisolated enum Config {
    /// Backend base URL. Swap in the real ngrok URL once the backend is up.
    /// While it still contains "REPLACE-ME", RouteService must use `Mocks` instead of the network.
    static let baseURL = "https://REPLACE-ME.ngrok-free.app"

    /// True once `baseURL` points at a real backend.
    static var isBackendConfigured: Bool { !baseURL.contains("REPLACE-ME") }

    /// `safety_weight` sent with every route request (0 = fastest, 1 = safest) until a slider exists.
    static let defaultSafetyWeight = 1.0

    /// Origin used when the user's location is unavailable: UT Austin, where the mock routes start.
    static let fallbackOrigin = CLLocationCoordinate2D(latitude: 30.2849, longitude: -97.7341)

    /// Pilot area: downtown Austin, TX. Map fallback before location is available, and search bias.
    static let austinCenter = CLLocationCoordinate2D(latitude: 30.2672, longitude: -97.7431)
    static let austinRegion = MKCoordinateRegion(
        center: austinCenter,
        latitudinalMeters: 12_000,
        longitudinalMeters: 12_000
    )
}
