//
//  SearchBar.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// Destination search with live suggestions, Apple Maps style. Once a route is showing, the field becomes
/// a two-line From / To panel with a swap button; tapping either line opens the same search for that end.
///
/// Focus is owned by the parent so tapping the map can dismiss the keyboard. The dropdown stays
/// open after the keyboard goes away (map tap or list scroll) until Cancel or a selection.
struct SearchBar: View {
    /// Which end of the route a search edits.
    enum Field {
        case origin, destination
    }

    /// What the From / To panel shows.
    struct Endpoints: Equatable {
        /// Nil means the user's location.
        var originName: String?
        var destinationName: String
        /// False when swapping would need the user's position and there is none yet.
        var canSwap: Bool
    }

    /// Used to bias suggestions toward the user; falls back to Austin.
    var userLocation: CLLocationCoordinate2D?
    /// Non-nil while a route is showing (or loading): the panel replaces the single field.
    var endpoints: Endpoints?
    var isFocused: FocusState<Bool>.Binding
    /// A place was picked for `field`. A nil item means "My Location" (origin only).
    var onSelect: (Field, MKMapItem?) -> Void
    var onSwap: () -> Void
    /// The clear (x) button was tapped: the parent returns the map to its neutral state.
    var onClear: () -> Void

    @State private var query = ""
    @State private var search = SearchService()
    /// True from the moment the field gains focus until Cancel or a selection.
    @State private var isActive = false
    /// Which end the open search is for. Always the destination in the neutral state.
    @State private var editing: Field = .destination

    private var showsNoResults: Bool {
        !query.isEmpty && search.hasSearched && search.suggestions.isEmpty && !search.isSearching
    }

    var body: some View {
        VStack(spacing: 8) {
            if let endpoints, !isActive {
                routePanel(endpoints)
            } else {
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
            }
            if isActive {
                if editing == .origin || !search.suggestions.isEmpty {
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
        .onChange(of: endpoints) { _, endpoints in
            // Back to the neutral state: the single field starts empty again.
            if endpoints == nil {
                editing = .destination
                query = ""
            }
        }
        .onSubmit {
            if let first = search.suggestions.first {
                select(first)
            }
        }
    }

    // MARK: - Single field

    private var field: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.primary)
            TextField(editing == .origin ? "Start from…" : "Where to?", text: $query)
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
                    if endpoints == nil {
                        onClear()
                    }
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

    // MARK: - From / To panel

    /// Swap on the left, centered between the two rows and well away from the clear button on the To row.
    private func routePanel(_ endpoints: Endpoints) -> some View {
        HStack(spacing: 6) {
            Button(action: onSwap) {
                Image(systemName: "arrow.up.arrow.down")
                    .font(.body.weight(.semibold))
                    .frame(width: 36, height: 44)
            }
            .buttonStyle(.plain)
            .disabled(!endpoints.canSwap)
            .accessibilityLabel("Swap start and destination")
            VStack(spacing: 0) {
                endpointRow(
                    .origin,
                    label: "From",
                    name: endpoints.originName ?? "My Location",
                    icon: endpoints.originName == nil ? .myLocation : .start
                )
                Divider()
                    .padding(.leading, 30)
                HStack(spacing: 8) {
                    endpointRow(.destination, label: "To", name: endpoints.destinationName, icon: .destination)
                    Button(action: onClear) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear route")
                }
            }
        }
        .padding(.leading, 6)
        .padding(.trailing, 14)
        .padding(.vertical, 2)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    /// Leading symbol of a panel row: blue location arrow for the user, green dot for a chosen start, red pin for the destination.
    private enum EndpointIcon {
        case myLocation, start, destination
    }

    @ViewBuilder
    private func icon(_ icon: EndpointIcon) -> some View {
        switch icon {
        case .myLocation:
            Image(systemName: "location.fill")
                .foregroundStyle(.blue)
        case .start:
            Circle()
                .fill(.green)
                .frame(width: 12, height: 12)
        case .destination:
            Image(systemName: "mappin.circle.fill")
                .foregroundStyle(.red)
        }
    }

    private func endpointRow(_ field: Field, label: String, name: String, icon: EndpointIcon) -> some View {
        Button {
            beginEditing(field)
        } label: {
            HStack(spacing: 10) {
                self.icon(icon)
                    .frame(width: 20)
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 40, alignment: .leading)
                Text(name)
                    .font(.body)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(label): \(name)")
        .accessibilityHint("Changes it")
    }

    // MARK: - Suggestions

    private var suggestionList: some View {
        ScrollView {
            VStack(spacing: 0) {
                if editing == .origin {
                    Button {
                        isFocused.wrappedValue = false
                        isActive = false
                        search.clear()
                        onSelect(.origin, nil)
                    } label: {
                        row(symbol: "location.fill", tint: .blue, title: AttributedString("My Location"), subtitle: nil)
                    }
                    .buttonStyle(.plain)
                    if !search.suggestions.isEmpty {
                        Divider().padding(.leading, 46)
                    }
                }
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
        return row(
            symbol: symbol.name,
            tint: symbol.isPin ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary),
            title: highlighted(completion.title, ranges: completion.titleHighlightRanges),
            subtitle: completion.subtitle.isEmpty ? nil : highlighted(completion.subtitle, ranges: completion.subtitleHighlightRanges)
        )
    }

    private func row(symbol: String, tint: some ShapeStyle, title: AttributedString, subtitle: AttributedString?) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(tint)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.body)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if let subtitle {
                    Text(subtitle)
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

    // MARK: - Actions

    /// Opens the search for one end of the route, starting from an empty field.
    private func beginEditing(_ field: Field) {
        editing = field
        query = ""
        search.clear()
        isActive = true
        isFocused.wrappedValue = true
    }

    private func select(_ completion: MKLocalSearchCompletion) {
        isFocused.wrappedValue = false
        isActive = false
        query = completion.title
        let field = editing
        Task {
            guard let item = await search.resolve(completion) else { return }
            search.clear()
            onSelect(field, item)
        }
    }

    /// Closes the search without picking anything; in the neutral state the typed text is kept.
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
