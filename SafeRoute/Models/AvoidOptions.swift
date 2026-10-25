//
//  AvoidOptions.swift
//  SafeRoute
//

import Foundation

/// Road types the user prefers to stay off: the optional `avoid` list in POST /route.
/// The backend treats it as a strong preference, not a ban, so a destination only reachable
/// by highway still gets a route; `X-Avoid-Applied` reports what it actually honoured.
nonisolated struct AvoidOptions: Equatable {
    var tolls = false
    var highways = false

    var isEmpty: Bool { !tolls && !highways }

    /// Exact wire values in the backend's canonical order; empty when nothing is avoided.
    var wireValues: [String] {
        var values: [String] = []
        if tolls { values.append("tolls") }
        if highways { values.append("highways") }
        return values
    }

    /// "tolls and highways", "tolls" or "highways"; nil when nothing is avoided.
    var listText: String? {
        switch (tolls, highways) {
        case (true, true): "tolls and highways"
        case (true, false): "tolls"
        case (false, true): "highways"
        case (false, false): nil
        }
    }
}

nonisolated extension AvoidOptions {
    /// Parses the `X-Avoid-Applied` header: `"tolls,highways"`, `"tolls"` or `"none"`. Unknown values are ignored.
    init(header: String?) {
        let values = Set((header ?? "").lowercased().split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
        self.init(tolls: values.contains("tolls"), highways: values.contains("highways"))
    }
}
