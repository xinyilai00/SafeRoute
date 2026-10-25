//
//  SearchService.swift
//  SafeRoute
//

import MapKit
import Observation

/// Live search suggestions (MKLocalSearchCompleter) resolved to a map item when one is picked.
/// MainActor by project default; completer callbacks are `nonisolated` and hop back.
@Observable
final class SearchService: NSObject, MKLocalSearchCompleterDelegate {
    private(set) var suggestions: [MKLocalSearchCompletion] = []
    /// True while the completer is working on the current text.
    private(set) var isSearching = false
    /// True while a picked suggestion is being turned into an `MKMapItem`.
    private(set) var isResolving = false
    /// True once the completer has answered for the current text (drives the "no results" row).
    private(set) var hasSearched = false

    @ObservationIgnored private let completer = MKLocalSearchCompleter()
    @ObservationIgnored private var isConfigured = false

    private func configureIfNeeded() {
        guard !isConfigured else { return }
        isConfigured = true
        completer.delegate = self
        completer.resultTypes = [.address, .pointOfInterest]
    }

    /// Updates suggestions for `query`, biased to `center` (the user) or Austin.
    func search(_ query: String, near center: CLLocationCoordinate2D?) {
        configureIfNeeded()
        completer.region = MKCoordinateRegion(
            center: center ?? Config.austinCenter,
            latitudinalMeters: 40_000,
            longitudinalMeters: 40_000
        )
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            clear()
            return
        }
        if completer.queryFragment == text {
            completer.queryFragment = "" // same text again (e.g. refocus): force a fresh callback
        }
        isSearching = true
        completer.queryFragment = text
    }

    /// Looks up the place behind a suggestion. Nil if MapKit finds nothing or the lookup fails.
    func resolve(_ completion: MKLocalSearchCompletion) async -> MKMapItem? {
        isResolving = true
        defer { isResolving = false }
        let response = try? await MKLocalSearch(request: MKLocalSearch.Request(completion: completion)).start()
        return response?.mapItems.first
    }

    func clear() {
        completer.cancel()
        completer.queryFragment = ""
        suggestions = []
        isSearching = false
        hasSearched = false
    }

    // MARK: - MKLocalSearchCompleterDelegate

    nonisolated func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        let results = completer.queryFragment.isEmpty ? [] : completer.results
        let answered = !completer.queryFragment.isEmpty
        Task { @MainActor in
            self.suggestions = results
            self.isSearching = false
            self.hasSearched = answered
        }
    }

    nonisolated func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        Task { @MainActor in
            self.suggestions = []
            self.isSearching = false
            self.hasSearched = true
        }
    }
}
