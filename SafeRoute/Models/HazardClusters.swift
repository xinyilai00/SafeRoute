//
//  HazardClusters.swift
//  SafeRoute
//

import CoreLocation
import Foundation
import MapKit

/// One map marker's worth of maneuver hazards: a single event, or several that sit close together.
nonisolated struct HazardCluster: Identifiable, Equatable {
    let events: [RiskEvent]
    let latitude: Double
    let longitude: Double

    var id: String { events.map(\.id).joined(separator: "|") }
    var count: Int { events.count }
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }

    /// The most serious hazard in the cluster decides the marker's icon and color.
    var primaryKind: RiskEventType {
        events.map(\.kind).max { $0.severityRank < $1.severityRank } ?? .unknown
    }
}

/// Decides which hazards the route overview marks, and merges the ones that would overlap.
nonisolated enum HazardClustering {
    /// Events within this many meters of each other on the other route count as the same maneuver.
    static let sharedManeuverMeters = 40.0
    /// Markers closer than this merge. Grows with route length so a long route does not end up speckled.
    static func mergeMeters(routeMeters: Double) -> Double {
        max(150, routeMeters * 0.025)
    }

    /// Overview markers: for two different routes, only the fastest route's hazards that the safe route
    /// does not also pass through (the safe line itself stays clean; drive mode calls out its hazards).
    /// For identical routes, that route's own maneuver hazards.
    static func overviewClusters(for response: RouteResponse) -> [HazardCluster] {
        if response.routesAreIdentical {
            return clusters(response.safest.maneuverEvents, routeMeters: response.safest.distanceKm * 1000)
        }
        let avoided = avoidedEvents(fastest: response.fastest, safest: response.safest)
        return clusters(avoided, routeMeters: response.fastest.distanceKm * 1000)
    }

    /// Fastest-route hazards with no safest-route hazard at (nearly) the same spot.
    static func avoidedEvents(fastest: Route, safest: Route) -> [RiskEvent] {
        let safePoints = safest.maneuverEvents.map { MKMapPoint($0.coordinate) }
        return fastest.maneuverEvents.filter { event in
            let point = MKMapPoint(event.coordinate)
            return !safePoints.contains { $0.distance(to: point) <= sharedManeuverMeters }
        }
    }

    /// Greedy merge: each event joins the first cluster whose center is within the merge distance,
    /// otherwise starts its own. Centers are recomputed as events join.
    static func clusters(_ events: [RiskEvent], routeMeters: Double) -> [HazardCluster] {
        let limit = mergeMeters(routeMeters: routeMeters)
        var groups: [(events: [RiskEvent], center: MKMapPoint)] = []
        for event in events {
            let point = MKMapPoint(event.coordinate)
            if let index = groups.firstIndex(where: { $0.center.distance(to: point) <= limit }) {
                groups[index].events.append(event)
                groups[index].center = centroid(of: groups[index].events)
            } else {
                groups.append((events: [event], center: point))
            }
        }
        return groups.map { group in
            let center = group.center.coordinate
            return HazardCluster(events: group.events, latitude: center.latitude, longitude: center.longitude)
        }
    }

    private static func centroid(of events: [RiskEvent]) -> MKMapPoint {
        let points = events.map { MKMapPoint($0.coordinate) }
        let count = Double(points.count)
        return MKMapPoint(x: points.map(\.x).reduce(0, +) / count, y: points.map(\.y).reduce(0, +) / count)
    }
}
