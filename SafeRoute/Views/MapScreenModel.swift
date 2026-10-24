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

    /// Crash-risk heatmap cells: fetched once per launch and cached here.
    private(set) var riskGrid: RiskGridState = .loading
    var showsRiskHeatmap = false

    enum RiskGridState {
        case loading
        case loaded([RiskCell])
        case failed
    }

    var riskCells: [RiskCell]? {
        if case .loaded(let cells) = riskGrid { return cells }
        return nil
    }

    /// False once the fetch failed; the toggle is hidden in that case.
    var isRiskGridAvailable: Bool {
        if case .failed = riskGrid { return false }
        return true
    }

    @ObservationIgnored private let routeService = RouteService()
    @ObservationIgnored private let riskService = RiskService()
    @ObservationIgnored private var routeTask: Task<Void, Never>?
    @ObservationIgnored private var riskTask: Task<Void, Never>?

    /// Fetches GET /risk the first time it is called; later calls are no-ops.
    func loadRiskGridIfNeeded() {
        guard riskTask == nil else { return }
        riskTask = Task {
            do {
                riskGrid = .loaded(try await riskService.fetchRiskCells())
            } catch {
                riskGrid = .failed
                print("MapScreenModel: risk grid unavailable, hiding heatmap toggle. \(error)")
            }
        }
    }

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
