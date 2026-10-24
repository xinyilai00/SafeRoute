//
//  SearchService.swift
//  SafeRoute
//

import MapKit
import Observation

/// Debounced place search backed by MKLocalSearch.
@Observable
final class SearchService {
    private(set) var results: [MKMapItem] = []
    private(set) var isSearching = false
    /// True after at least one search completed for the current text (drives the "no results" row).
    private(set) var hasSearched = false

    @ObservationIgnored private var searchTask: Task<Void, Never>?

    /// Searches for `query` near `center` (defaults to Austin). Cancels any in-flight search.
    func search(_ query: String, near center: CLLocationCoordinate2D?, immediately: Bool = false) {
        searchTask?.cancel()
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count >= 2 else {
            results = []
            isSearching = false
            hasSearched = false
            return
        }

        searchTask = Task {
            if !immediately {
                try? await Task.sleep(for: .milliseconds(300))
            }
            guard !Task.isCancelled else { return }

            let request = MKLocalSearch.Request()
            request.naturalLanguageQuery = text
            request.resultTypes = [.pointOfInterest, .address]
            request.region = MKCoordinateRegion(
                center: center ?? Config.austinCenter,
                latitudinalMeters: 30_000,
                longitudinalMeters: 30_000
            )

            isSearching = true
            defer { isSearching = false }
            do {
                let response = try await MKLocalSearch(request: request).start()
                guard !Task.isCancelled else { return }
                results = Array(response.mapItems.prefix(8))
            } catch {
                guard !Task.isCancelled else { return }
                results = []
            }
            hasSearched = true
        }
    }

    func clear() {
        searchTask?.cancel()
        results = []
        isSearching = false
        hasSearched = false
    }
}
