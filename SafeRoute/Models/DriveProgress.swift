//
//  DriveProgress.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// Pure drive-mode state machine: where the driver is on the route, which hazard is next, and what
/// to announce. `DriveModel` feeds it fixes and speaks what it returns, so this part is testable.
nonisolated struct DriveProgress {
    enum Status: Equatable {
        case driving
        case offRoute
        case arrived
    }

    /// Something to tell the driver.
    enum Alert: Equatable {
        /// About a quarter mile before a hazard.
        case hazardAhead(RiskEvent)
        /// About 500 feet before a hazard.
        case hazardClose(RiskEvent)
        case offRoute
        case arrived
    }

    struct Hazard: Equatable {
        let event: RiskEvent
        /// Meters from the start of the route.
        let distanceAlong: Double
    }

    static let farAlertMeters = 402.0      // about a quarter mile
    static let nearAlertMeters = 152.0     // about 500 feet
    static let arrivalMeters = 30.0
    static let offRouteMeters = 75.0
    static let offRouteUpdatesNeeded = 3
    /// A hazard this close ahead of the projected point counts as reached, not upcoming.
    static let passedSlackMeters = 15.0

    let destination: CLLocationCoordinate2D
    private(set) var etaMinutes: Double
    private(set) var track: RouteTrack
    /// Maneuver hazards on the route (no crash zones), nearest the start first.
    private(set) var hazards: [Hazard]
    private(set) var position: RouteTrack.Position?
    private(set) var status: Status = .driving
    /// Per hazard id: 1 once the quarter-mile alert was given, 2 once the 500-foot alert was.
    private var alertStage: [String: Int] = [:]
    private var offRouteUpdates = 0

    init(route: Route, destination: CLLocationCoordinate2D) {
        self.destination = destination
        etaMinutes = route.etaMinutes
        track = RouteTrack(coordinates: route.coordinates)
        hazards = Self.hazards(of: route, on: track)
    }

    var totalMeters: Double { track.totalMeters }

    var remainingMeters: Double? {
        position.map { max(0, track.totalMeters - $0.distanceAlong) }
    }

    /// The route's ETA scaled by the distance left.
    var remainingMinutes: Double? {
        remainingMeters.map { track.totalMeters > 0 ? etaMinutes * $0 / track.totalMeters : 0 }
    }

    /// The first hazard ahead of the driver along the route, and how far ahead it is.
    var nextHazard: (event: RiskEvent, metersAhead: Double)? {
        guard let position else { return nil }
        return hazards
            .first { $0.distanceAlong > position.distanceAlong + Self.passedSlackMeters }
            .map { ($0.event, $0.distanceAlong - position.distanceAlong) }
    }

    /// Projects one fix onto the route and returns what should be announced because of it.
    mutating func update(with coordinate: CLLocationCoordinate2D) -> [Alert] {
        guard status != .arrived,
              let projected = track.position(nearest: coordinate, after: position?.distanceAlong) else { return [] }
        position = projected

        let toDestination = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
            .distance(from: CLLocation(latitude: destination.latitude, longitude: destination.longitude))
        let toRouteEnd = track.totalMeters - projected.distanceAlong
        if toDestination <= Self.arrivalMeters || (toRouteEnd <= Self.arrivalMeters && projected.offRouteMeters <= Self.arrivalMeters) {
            status = .arrived
            return [.arrived]
        }

        var alerts: [Alert] = []
        if projected.offRouteMeters > Self.offRouteMeters {
            offRouteUpdates += 1
            if offRouteUpdates >= Self.offRouteUpdatesNeeded, status != .offRoute {
                status = .offRoute
                alerts.append(.offRoute)
            }
        } else {
            offRouteUpdates = 0
            status = .driving
        }

        guard status == .driving, let next = nextHazard else { return alerts }
        let stage = alertStage[next.event.id] ?? 0
        if next.metersAhead <= Self.nearAlertMeters, stage < 2 {
            alertStage[next.event.id] = 2
            alerts.append(.hazardClose(next.event))
        } else if next.metersAhead <= Self.farAlertMeters, stage < 1 {
            alertStage[next.event.id] = 1
            alerts.append(.hazardAhead(next.event))
        }
        return alerts
    }

    /// Switches to a new route after a reroute. Progress and announcements start over.
    mutating func replaceRoute(_ route: Route) {
        etaMinutes = route.etaMinutes
        track = RouteTrack(coordinates: route.coordinates)
        hazards = Self.hazards(of: route, on: track)
        position = nil
        status = .driving
        alertStage = [:]
        offRouteUpdates = 0
    }

    private static func hazards(of route: Route, on track: RouteTrack) -> [Hazard] {
        route.maneuverEvents
            .compactMap { event in
                track.position(nearest: event.coordinate).map { Hazard(event: event, distanceAlong: $0.distanceAlong) }
            }
            .sorted { $0.distanceAlong < $1.distanceAlong }
    }
}

/// Text for the drive-mode UI and speech.
nonisolated enum DriveFormat {
    /// "450 ft" under about 950 feet (rounded to 50), otherwise "0.2 mi" / "12 mi".
    static func distance(meters: Double) -> String {
        let feet = meters * 3.28084
        if feet < 950 {
            return "\(max(50, Int((feet / 50).rounded()) * 50)) ft"
        }
        let miles = meters / 1609.344
        return miles < 10 ? String(format: "%.1f mi", miles) : "\(Int(miles.rounded())) mi"
    }

    /// "12 min" or "1 hr 5 min"; never less than a minute.
    static func duration(minutes: Double) -> String {
        let total = max(1, Int(minutes.rounded()))
        return total < 60 ? "\(total) min" : "\(total / 60) hr \(total % 60) min"
    }

    static func clockTime(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    /// "Busy left turn", for the banner.
    static func hazardTitle(_ event: RiskEvent) -> String {
        let name = event.kind.friendlyName(count: 1)
        return name.prefix(1).uppercased() + name.dropFirst()
    }

    /// What the speaker says for an alert.
    static func phrase(for alert: DriveProgress.Alert) -> String {
        switch alert {
        case .hazardAhead(let event): "In a quarter mile, \(event.kind.friendlyName(count: 1))."
        case .hazardClose(let event): "In 500 feet, \(event.kind.friendlyName(count: 1))."
        case .offRoute: "Off route. Finding a new route."
        case .arrived: "You have arrived."
        }
    }
}
