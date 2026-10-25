//
//  RouteLabels.swift
//  SafeRoute
//

import CoreLocation
import MapKit
import SwiftUI

/// Small capsule pinned to a route line, e.g. "Safe · 24 min".
struct RouteLabel: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption.weight(.bold))
            .foregroundStyle(.white)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(color, in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(0.9), lineWidth: 1.5))
            .shadow(color: .black.opacity(0.2), radius: 2, y: 1)
            .padding(.bottom, 8) // float just above the line (annotation anchor is .bottom)
            .allowsHitTesting(false)
    }
}

/// Where to pin each route's label.
nonisolated struct RouteLabelAnchors {
    let safe: CLLocationCoordinate2D
    /// Nil when the routes are identical and only one label is shown.
    let fast: CLLocationCoordinate2D?
}

/// Puts each label where the two routes are farthest apart so they never sit on top of each other.
nonisolated enum RouteLabelPlacement {
    static func anchors(for response: RouteResponse) -> RouteLabelAnchors? {
        let safe = response.safest.coordinates
        let fast = response.fastest.coordinates
        guard !safe.isEmpty else { return nil }
        if response.routesAreIdentical {
            return RouteLabelAnchors(safe: safe[safe.count / 2], fast: nil)
        }
        guard let safeAnchor = farthestPoint(of: safe, from: fast),
              let fastAnchor = farthestPoint(of: fast, from: safe) else { return nil }
        return RouteLabelAnchors(safe: safeAnchor, fast: fastAnchor)
    }

    /// The vertex of `route` farthest from every vertex of `other`. Both are subsampled to keep it cheap.
    private static func farthestPoint(of route: [CLLocationCoordinate2D],
                                      from other: [CLLocationCoordinate2D]) -> CLLocationCoordinate2D? {
        guard !route.isEmpty, !other.isEmpty else { return nil }
        let candidates = subsample(route, to: 150)
        let reference = subsample(other, to: 150).map(MKMapPoint.init)
        var best: (distance: Double, coordinate: CLLocationCoordinate2D)?
        for coordinate in candidates {
            let point = MKMapPoint(coordinate)
            var nearest = Double.greatestFiniteMagnitude
            for ref in reference {
                nearest = min(nearest, point.distance(to: ref))
            }
            if best == nil || nearest > best!.distance {
                best = (nearest, coordinate) // keep the original vertex, not a round-tripped MKMapPoint
            }
        }
        return best?.coordinate
    }

    private static func subsample(_ points: [CLLocationCoordinate2D], to count: Int) -> [CLLocationCoordinate2D] {
        guard points.count > count, count > 1 else { return points }
        let step = Double(points.count - 1) / Double(count - 1)
        return (0..<count).map { points[Int((Double($0) * step).rounded())] }
    }
}
