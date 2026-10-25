//
//  RiskService.swift
//  SafeRoute
//

import Foundation

/// Fetches the crash-risk grid (GET /risk) and prepares it for drawing.
/// No mock: if this fails the heatmap toggle is hidden.
nonisolated struct RiskService {
    /// Runs off the main actor: the payload is around 1 MB and tracing and smoothing the zones is CPU work.
    @concurrent
    func fetchHeatmap(minRisk: Double = Config.riskMinimum) async throws -> [HeatBand] {
        guard Config.isBackendConfigured,
              var components = URLComponents(string: Config.baseURL + "/risk") else {
            throw BackendError.badURL
        }
        components.queryItems = [URLQueryItem(name: "min_risk", value: String(minRisk))]
        guard let url = components.url else { throw BackendError.badURL }

        var request = URLRequest(url: url, timeoutInterval: 20)
        request.setValue("application/geo+json, application/json", forHTTPHeaderField: "Accept")
        // Free-tier ngrok shows an HTML interstitial unless this header is present.
        request.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")

        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError.badStatus(http.statusCode)
        }
        let cells = try JSONDecoder().decode(RiskFeatureCollection.self, from: data).cells
        let bands = RiskHeatmap.bands(from: cells, minimum: minRisk)
        let zones = bands.reduce(0) { $0 + $1.zones.count }
        let points = bands.reduce(0) { $0 + $1.pointCount }
        print("RiskService: \(cells.count) cells -> \(zones) heat zones in \(bands.count) bands, \(points) points")
        return bands
    }
}
