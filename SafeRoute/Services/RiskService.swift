//
//  RiskService.swift
//  SafeRoute
//

import Foundation

/// Loads the heatmap cells from GET /risk, falling back to the bundled sample (`Mocks.riskGridJSON`)
/// when the backend is unconfigured or the request fails.
nonisolated struct RiskService {
    /// Cells below this risk are not requested: it keeps the polygon count (and the download) small.
    static let minRisk = 0.45

    private let decoder = JSONDecoder()

    func fetchCells() async -> (cells: [RiskCell], isDemoData: Bool) {
        if Config.isBackendConfigured, let cells = try? await fetchFromBackend() {
            return (cells, false)
        }
        let sample = (try? decoder.decode(RiskGridResponse.self, from: Mocks.riskGridJSON))
            .map(RiskCell.cells(from:)) ?? []
        return (sample, true)
    }

    private func fetchFromBackend() async throws -> [RiskCell] {
        guard let url = URL(string: Config.baseURL + "/risk?min_risk=\(Self.minRisk)") else {
            throw RouteServiceError.badURL
        }
        var request = URLRequest(url: url, timeoutInterval: 20)
        request.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw RouteServiceError.badStatus(http.statusCode)
        }
        return RiskCell.cells(from: try decoder.decode(RiskGridResponse.self, from: data))
    }
}
