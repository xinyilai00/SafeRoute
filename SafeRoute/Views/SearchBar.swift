//
//  SearchBar.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// Destination search field with a dropdown of MKLocalSearch results.
struct SearchBar: View {
    /// Used to bias results toward the user; falls back to Austin.
    var userLocation: CLLocationCoordinate2D?
    var onSelect: (MKMapItem) -> Void

    @State private var query = ""
    @State private var search = SearchService()
    @FocusState private var isFocused: Bool

    private var showsNoResults: Bool {
        search.hasSearched && search.results.isEmpty && !search.isSearching
    }

    var body: some View {
        VStack(spacing: 8) {
            field
            if isFocused {
                if !search.results.isEmpty {
                    resultsList
                } else if showsNoResults {
                    Text("No places found")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
            }
        }
        .onChange(of: query) { _, newValue in
            guard isFocused else { return }
            search.search(newValue, near: userLocation)
        }
        .onSubmit {
            search.search(query, near: userLocation, immediately: true)
        }
    }

    private var field: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Where to?", text: $query)
                .focused($isFocused)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled()
                .submitLabel(.search)
            if search.isSearching {
                ProgressView()
                    .controlSize(.small)
            } else if !query.isEmpty {
                Button {
                    query = ""
                    search.clear()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 8, y: 2)
    }

    private var resultsList: some View {
        VStack(spacing: 0) {
            ForEach(Array(search.results.enumerated()), id: \.element) { index, item in
                Button {
                    select(item)
                } label: {
                    row(item)
                }
                .buttonStyle(.plain)
                if index < search.results.count - 1 {
                    Divider().padding(.leading, 46)
                }
            }
        }
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 8, y: 2)
    }

    private func row(_ item: MKMapItem) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "mappin.circle.fill")
                .font(.title3)
                .foregroundStyle(.red)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name ?? "Unknown place")
                    .font(.body)
                    .foregroundStyle(.primary)
                if let address = item.address?.shortAddress ?? item.address?.fullAddress {
                    Text(address)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }

    private func select(_ item: MKMapItem) {
        isFocused = false
        query = item.name ?? ""
        search.clear()
        onSelect(item)
    }
}
