//
//  RiskService.swift
//  SafeRoute
//

import Foundation

/// Fetches the crash-risk grid (GET /risk). No mock: if this fails the heatmap toggle is hidden.
nonisolated struct RiskService {
    /// Decodes off the main actor; the payload is about 1 MB at the default threshold.
    @concurrent
    func fetchRiskCells(minRisk: Double = Config.riskMinimum) async throws -> [RiskCell] {
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
        return try JSONDecoder().decode(RiskFeatureCollection.self, from: data).cells
    }
}
