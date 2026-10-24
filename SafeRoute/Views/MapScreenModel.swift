//
//  MapScreenModel.swift
//  SafeRoute
//

import CoreLocation
import MapKit
import Observation

/// State for `MapScreen`: chosen destination, profile, and the current route result.
@Observable
final class MapScreenModel {
    var profile: Profile = .teen
    private(set) var destination: MKMapItem?
    private(set) var result: RouteResult?
    private(set) var isLoading = false

    @ObservationIgnored private let routeService = RouteService()
    @ObservationIgnored private var routeTask: Task<Void, Never>?

    /// Picking a destination clears any routes for the previous one.
    func selectDestination(_ item: MKMapItem) {
        routeTask?.cancel()
        destination = item
        result = nil
        isLoading = false
    }

    /// Requests fastest + safest routes for the current destination and profile.
    /// `origin` is the user's location; when unavailable the UT Austin fallback keeps the demo working.
    func findRoute(from origin: CLLocationCoordinate2D?) {
        guard let destination else { return }
        routeTask?.cancel()

        let originCoordinate = origin ?? Config.fallbackOrigin
        let destinationCoordinate = destination.location.coordinate
        let profile = profile
        isLoading = true

        routeTask = Task {
            do {
                let result = try await routeService.fetchRoute(
                    origin: originCoordinate,
                    destination: destinationCoordinate,
                    profile: profile
                )
                guard !Task.isCancelled else { return }
                self.result = result
            } catch {
                guard !Task.isCancelled else { return }
                // RouteService already fell back to Mocks; reaching here means even the mock failed to decode.
                print("MapScreenModel: route request failed. \(error)")
            }
            isLoading = false
        }
    }
}
