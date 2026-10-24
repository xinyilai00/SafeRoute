//
//  LocationManager.swift
//  SafeRoute
//

import CoreLocation
import Observation

/// Requests When-In-Use permission and streams the user's location.
/// The whole type is MainActor-isolated (project default); delegate callbacks are
/// `nonisolated` and hop back to the main actor before touching state.
@Observable
final class LocationManager: NSObject, CLLocationManagerDelegate {
    private(set) var location: CLLocation?
    private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined

    @ObservationIgnored private let manager = CLLocationManager()
    @ObservationIgnored private var isConfigured = false

    var coordinate: CLLocationCoordinate2D? { location?.coordinate }

    var isAuthorized: Bool {
        authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways
    }

    /// Prompts for permission if needed, then starts location updates. Safe to call repeatedly.
    func start() {
        if !isConfigured {
            isConfigured = true
            manager.delegate = self
            manager.desiredAccuracy = kCLLocationAccuracyBest
            manager.distanceFilter = 10
        }
        authorizationStatus = manager.authorizationStatus
        switch authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            manager.startUpdatingLocation()
        default:
            break
        }
    }

    // MARK: - CLLocationManagerDelegate

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            self.authorizationStatus = status
            if self.isAuthorized {
                self.manager.startUpdatingLocation()
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let latest = locations.last else { return }
        Task { @MainActor in
            self.location = latest
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Transient errors (e.g. kCLErrorLocationUnknown) are expected; keep the last known fix.
    }
}
