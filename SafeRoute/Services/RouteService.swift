//
//  RouteService.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// A decoded route response plus whether it came from `Mocks` instead of the backend.
nonisolated struct RouteResult: Equatable {
    let response: RouteResponse
    let isDemoData: Bool
}

/// Errors shared by the backend services.
nonisolated enum BackendError: Error {
    case badURL
    case badStatus(Int)
}

/// Calls POST /route. Falls back to `Mocks` whenever the backend is not configured or the request fails,
/// so the UI always has something to show. Cancellation is never swallowed.
nonisolated struct RouteService {
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    func fetchRoute(
        origin: CLLocationCoordinate2D,
        destination: CLLocationCoordinate2D,
        profile: Profile,
        safetyWeight: Double = Config.defaultSafetyWeight,
        avoid: [String] = []
    ) async throws -> RouteResult {
        guard Config.isBackendConfigured else {
            // Demo path: pause briefly so the loading state is visible; the mock would otherwise return instantly.
            try await Task.sleep(for: .milliseconds(700))
            return try mockResult(for: profile)
        }

        do {
            let body = RouteRequest(
                origin: Coordinate(origin),
                destination: Coordinate(destination),
                profile: profile,
                safetyWeight: safetyWeight,
                avoid: avoid
            )
            guard let url = URL(string: Config.baseURL + "/route") else { throw BackendError.badURL }
            var request = URLRequest(url: url, timeoutInterval: 10)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            // Free-tier ngrok shows an HTML interstitial unless this header is present.
            request.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")
            request.httpBody = try encoder.encode(body)

            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                throw BackendError.badStatus(http.statusCode)
            }
            return RouteResult(response: try decoder.decode(RouteResponse.self, from: data), isDemoData: false)
        } catch let error as URLError where error.code == .cancelled {
            throw error
        } catch let error as CancellationError {
            throw error
        } catch {
            if Task.isCancelled { throw error }
            print("RouteService: backend request failed, using demo data. \(error)")
            return try mockResult(for: profile)
        }
    }

    private func mockResult(for profile: Profile) throws -> RouteResult {
        let response = try decoder.decode(RouteResponse.self, from: Mocks.routeResponseJSON(for: profile))
        return RouteResult(response: response, isDemoData: true)
    }
}
