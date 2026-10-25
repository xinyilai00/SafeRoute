//
//  MapScreenModel.swift
//  SafeRoute
//

import CoreLocation
import MapKit
import Observation

/// State for `MapScreen`: chosen start and destination, profile, and the current route result.
@Observable
final class MapScreenModel {
    var profile: Profile = .teen
    /// Start of the route when it is not the user's location.
    private(set) var origin: MKMapItem?
    private(set) var destination: MKMapItem?
    private(set) var result: RouteResult?
    private(set) var isLoading = false
    /// True when the start or destination is outside the backend's Austin pilot area; no route is requested.
    private(set) var isOutsideCoverage = false

    /// Crash-risk heatmap, fetched once per launch and cached here already banded and merged.
    private(set) var riskGrid: RiskGridState = .loading
    var showsRiskHeatmap = false

    enum RiskGridState {
        case loading
        case loaded([HeatBand])
        case failed
    }

    var riskBands: [HeatBand]? {
        if case .loaded(let bands) = riskGrid { return bands }
        return nil
    }

    /// False once the fetch failed; the toggle is hidden in that case.
    var isRiskGridAvailable: Bool {
        if case .failed = riskGrid { return false }
        return true
    }

    /// True while the route starts where the user is (the default).
    var startsAtUserLocation: Bool { origin == nil }

    @ObservationIgnored private let routeService = RouteService()
    @ObservationIgnored private let riskService = RiskService()
    @ObservationIgnored private var routeTask: Task<Void, Never>?
    @ObservationIgnored private var riskTask: Task<Void, Never>?
    /// The "My Location" place a swap created, so swapping back restores the live user location as the start.
    @ObservationIgnored private var userLocationItem: MKMapItem?

    /// Fetches GET /risk the first time it is called; later calls are no-ops.
    func loadRiskGridIfNeeded() {
        guard riskTask == nil else { return }
        riskTask = Task {
            do {
                riskGrid = .loaded(try await riskService.fetchHeatmap())
            } catch {
                riskGrid = .failed
                print("MapScreenModel: risk grid unavailable, hiding heatmap toggle. \(error)")
            }
        }
    }

    /// Picking a destination clears any routes for the previous one. The start is kept.
    func selectDestination(_ item: MKMapItem) {
        routeTask?.cancel()
        destination = item
        result = nil
        isLoading = false
        isOutsideCoverage = false
    }

    /// Picks where the route starts; nil means the user's location. The old route stays up until the new one arrives.
    func selectOrigin(_ item: MKMapItem?) {
        origin = item
    }

    /// Swaps start and destination. When the start is the user's location, the destination becomes a
    /// "My Location" place at the user's position as of now; without a position the swap is skipped.
    /// Swapping back turns that place into the live user location again, so the start is My Location (not a preview).
    func swapEndpoints(userLocation: CLLocation?) {
        guard let destination else { return }
        let newDestination: MKMapItem
        if let origin {
            newDestination = origin
        } else {
            guard let userLocation else { return }
            newDestination = MKMapItem(location: userLocation, address: nil)
            newDestination.name = "My Location"
            userLocationItem = newDestination
        }
        origin = destination === userLocationItem ? nil : destination
        self.destination = newDestination
    }

    /// Back to the neutral state: no destination, routes, markers or card, and the start is the user again.
    func clearDestination() {
        routeTask?.cancel()
        origin = nil
        destination = nil
        userLocationItem = nil
        result = nil
        isLoading = false
        isOutsideCoverage = false
    }

    /// Requests fastest + safest routes for the current start, destination, profile and route options.
    /// `userLocation` is used when the start is the user; when unavailable the UT Austin fallback keeps the demo working.
    /// Points outside the pilot area get the coverage message instead of a request (the backend would answer 422).
    func findRoute(from userLocation: CLLocationCoordinate2D?, avoiding avoid: AvoidOptions = AvoidOptions()) {
        guard let destination else { return }
        routeTask?.cancel()

        let originCoordinate = origin?.location.coordinate ?? userLocation ?? Config.fallbackOrigin
        let destinationCoordinate = destination.location.coordinate
        guard Config.isInPilotArea(originCoordinate), Config.isInPilotArea(destinationCoordinate) else {
            result = nil
            isLoading = false
            isOutsideCoverage = true
            return
        }
        isOutsideCoverage = false
        let profile = profile
        isLoading = true

        routeTask = Task {
            do {
                let result = try await routeService.fetchRoute(
                    origin: originCoordinate,
                    destination: destinationCoordinate,
                    profile: profile,
                    avoiding: avoid
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
