//
//  SearchBar.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// Destination search field with live suggestions, Apple Maps style.
///
/// Focus is owned by the parent so tapping the map can dismiss the keyboard. The dropdown stays
/// open after the keyboard goes away (map tap or list scroll) until Cancel or a selection.
struct SearchBar: View {
    /// Used to bias suggestions toward the user; falls back to Austin.
    var userLocation: CLLocationCoordinate2D?
    var isFocused: FocusState<Bool>.Binding
    var onSelect: (MKMapItem) -> Void
    /// The clear (x) button was tapped: the parent returns the map to its neutral state.
    var onClear: () -> Void

    @State private var query = ""
    @State private var search = SearchService()
    /// True from the moment the field gains focus until Cancel or a selection.
    @State private var isActive = false

    private var showsNoResults: Bool {
        !query.isEmpty && search.hasSearched && search.suggestions.isEmpty && !search.isSearching
    }

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 12) {
                field
                if isActive {
                    Button("Cancel") {
                        cancel()
                    }
                    .font(.body)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }
            if isActive {
                if !search.suggestions.isEmpty {
                    suggestionList
                } else if showsNoResults {
                    Text("No places found")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
            }
        }
        .animation(.snappy(duration: 0.25), value: isActive)
        .onChange(of: isFocused.wrappedValue) { _, focused in
            guard focused else { return }
            isActive = true
            if search.suggestions.isEmpty {
                search.search(query, near: userLocation)
            }
        }
        .onChange(of: query) { _, newValue in
            guard isFocused.wrappedValue else { return }
            search.search(newValue, near: userLocation)
        }
        .onSubmit {
            if let first = search.suggestions.first {
                select(first)
            }
        }
    }

    private var field: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.primary)
            TextField("Where to?", text: $query)
                .focused(isFocused)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled()
                .submitLabel(.search)
            if search.isSearching || search.isResolving {
                ProgressView()
                    .controlSize(.small)
            } else if !query.isEmpty {
                Button {
                    query = ""
                    search.clear()
                    onClear()
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
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var suggestionList: some View {
        ScrollView {
            VStack(spacing: 0) {
                ForEach(Array(search.suggestions.enumerated()), id: \.element) { index, completion in
                    Button {
                        select(completion)
                    } label: {
                        row(completion)
                    }
                    .buttonStyle(.plain)
                    if index < search.suggestions.count - 1 {
                        Divider().padding(.leading, 46)
                    }
                }
            }
        }
        .frame(maxHeight: 360)
        .fixedSize(horizontal: false, vertical: true)
        .scrollDismissesKeyboard(.immediately)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func row(_ completion: MKLocalSearchCompletion) -> some View {
        let symbol = SuggestionSymbol.symbol(for: completion)
        return HStack(spacing: 12) {
            Image(systemName: symbol.name)
                .font(.title3)
                .foregroundStyle(symbol.isPin ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(highlighted(completion.title, ranges: completion.titleHighlightRanges))
                    .font(.body)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if !completion.subtitle.isEmpty {
                    Text(highlighted(completion.subtitle, ranges: completion.subtitleHighlightRanges))
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

    /// Bolds the parts of a suggestion that match what was typed.
    private func highlighted(_ text: String, ranges: [NSValue]) -> AttributedString {
        var attributed = AttributedString(text)
        for value in ranges {
            guard let range = Range(value.rangeValue, in: text),
                  let lower = AttributedString.Index(range.lowerBound, within: attributed),
                  let upper = AttributedString.Index(range.upperBound, within: attributed) else { continue }
            attributed[lower..<upper].font = .body.weight(.semibold)
        }
        return attributed
    }

    private func select(_ completion: MKLocalSearchCompletion) {
        isFocused.wrappedValue = false
        isActive = false
        query = completion.title
        Task {
            guard let item = await search.resolve(completion) else { return }
            search.clear()
            onSelect(item)
        }
    }

    /// Closes the search without picking anything; the typed text is kept.
    private func cancel() {
        isFocused.wrappedValue = false
        isActive = false
        search.clear()
    }
}

/// Picks an SF Symbol for a suggestion. MapKit gives no category, so this reads the title.
private enum SuggestionSymbol {
    struct Choice {
        let name: String
        /// Pins are drawn red like a map marker; category icons use the secondary color.
        let isPin: Bool
    }

    private static let keywords: [(String, String)] = [
        ("airport", "airplane"), ("park", "tree.fill"), ("trail", "figure.hiking"),
        ("university", "graduationcap.fill"), ("college", "graduationcap.fill"), ("school", "graduationcap.fill"),
        ("hospital", "cross.case.fill"), ("medical", "cross.case.fill"), ("clinic", "cross.case.fill"),
        ("coffee", "cup.and.saucer.fill"), ("cafe", "cup.and.saucer.fill"), ("café", "cup.and.saucer.fill"),
        ("restaurant", "fork.knife"), ("grill", "fork.knife"), ("kitchen", "fork.knife"), ("taco", "fork.knife"),
        ("pizza", "fork.knife"), ("bbq", "fork.knife"), ("barbecue", "fork.knife"), ("burger", "fork.knife"),
        ("bar", "wineglass.fill"), ("brewery", "wineglass.fill"),
        ("hotel", "bed.double.fill"), ("inn", "bed.double.fill"),
        ("library", "books.vertical.fill"), ("museum", "building.columns.fill"), ("capitol", "building.columns.fill"),
        ("church", "building.fill"), ("stadium", "sportscourt.fill"), ("gym", "dumbbell.fill"),
        ("mall", "bag.fill"), ("market", "cart.fill"), ("grocery", "cart.fill"), ("h-e-b", "cart.fill"),
        ("station", "tram.fill"), ("gas", "fuelpump.fill"), ("bank", "banknote.fill"),
        ("pharmacy", "pills.fill"), ("theater", "theatermasks.fill"), ("theatre", "theatermasks.fill"),
    ]

    static func symbol(for completion: MKLocalSearchCompletion) -> Choice {
        let title = completion.title.lowercased()
        if title.first?.isNumber == true {
            return Choice(name: "mappin.and.ellipse", isPin: true) // street address
        }
        for (keyword, name) in keywords where title.contains(keyword) {
            return Choice(name: name, isPin: false)
        }
        return Choice(name: "mappin.circle.fill", isPin: true)
    }
}
