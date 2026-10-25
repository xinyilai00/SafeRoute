//
//  DriveModel.swift
//  SafeRoute
//

import CoreLocation
import Foundation
import Observation

/// Where the drive-mode camera looks: a point on the route ahead of the car, turned to the route's direction.
nonisolated struct DriveCamera: Equatable {
    var latitude: Double
    var longitude: Double
    var heading: Double

    var center: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }
}

/// The car's position and direction for the on-map arrow.
nonisolated struct DriveCar: Equatable {
    var latitude: Double
    var longitude: Double
    /// Degrees clockwise from north.
    var bearing: Double

    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }
}

/// Numbers for the bottom bar.
nonisolated struct DriveStats: Equatable {
    var remainingMinutes: Double
    var remainingMeters: Double
    var arrival: Date
}

/// State for one drive along the safe route: progress, camera target, banner and spoken alerts.
@Observable
final class DriveModel {
    /// What the top banner shows.
    enum Banner: Equatable {
        case hazard(RiskEvent, metersAhead: Double)
        /// Nothing ahead on the route.
        case clear
        case offRoute
        case arrived
    }

    /// Demo drive: a fake position moves along the route instead of real fixes.
    let isSimulated: Bool
    private(set) var route: Route
    private(set) var progress: DriveProgress
    private(set) var camera: DriveCamera?
    /// Where to draw the car arrow; snapped to the route when close to it.
    private(set) var car: DriveCar?
    private(set) var isMuted = false
    /// Increments with every alert (spoken or not), driving the haptic.
    private(set) var alertCount = 0
    /// Increments when a new route should be requested from the current location.
    private(set) var rerouteRequests = 0
    /// True a few seconds after arrival; the screen then leaves drive mode.
    private(set) var isFinished = false

    @ObservationIgnored private let speaker = DriveSpeaker()
    @ObservationIgnored private var lastLocation: CLLocation?
    @ObservationIgnored private var lastRerouteAt: Date?
    @ObservationIgnored private var finishTask: Task<Void, Never>?
    @ObservationIgnored private var simulationTask: Task<Void, Never>?

    /// Minimum gap between reroute requests, so a route that cannot be matched does not loop.
    private static let rerouteInterval: TimeInterval = 30
    /// Simulated drives run this many times faster than the route's own ETA implies.
    private static let simulationSpeedFactor = 4.0
    private static let simulationTick: TimeInterval = 0.5
    /// The camera heading is the route's direction over this many meters ahead, so it does not jitter at vertices.
    private static let headingLookAheadMeters = 50.0
    /// The camera looks at the route this far ahead of the car, which puts the car in the lower third of the screen.
    private static let centerAheadMeters = 80.0
    /// Within this distance of the route the car and camera are snapped onto it.
    private static let snapMeters = 30.0

    init(route: Route, destination: CLLocationCoordinate2D, simulated: Bool = false) {
        isSimulated = simulated
        self.route = route
        progress = DriveProgress(route: route, destination: destination)
        // Until the first fix arrives, the car sits at the start of the route, facing down it.
        if let start = progress.track.position(atDistance: 0) {
            car = DriveCar(latitude: start.latitude, longitude: start.longitude, bearing: start.bearing)
            camera = cameraOnRoute(at: start)
        }
        if simulated {
            startSimulation()
        }
    }

    /// Moves a fake position along the route at about 4x the route's average speed, feeding it through
    /// `update(with:)` so camera, banner, speech and arrival behave exactly as on a real drive.
    private func startSimulation() {
        let total = progress.totalMeters
        guard total > 0, progress.etaMinutes > 0 else { return }
        let speed = Self.simulationSpeedFactor * total / (progress.etaMinutes * 60)
        simulationTask = Task { [weak self] in
            var distance = 0.0
            while !Task.isCancelled {
                guard let self, let point = progress.track.position(atDistance: distance) else { return }
                let location = CLLocation(
                    coordinate: point.coordinate, altitude: 0, horizontalAccuracy: 5, verticalAccuracy: -1,
                    course: point.bearing, speed: speed, timestamp: .now
                )
                update(with: location)
                if progress.status == .arrived { return }
                distance += speed * Self.simulationTick
                try? await Task.sleep(for: .seconds(Self.simulationTick))
            }
        }
    }

    var banner: Banner {
        switch progress.status {
        case .arrived: .arrived
        case .offRoute: .offRoute
        case .driving: progress.nextHazard.map { .hazard($0.event, metersAhead: $0.metersAhead) } ?? .clear
        }
    }

    var stats: DriveStats? {
        guard let meters = progress.remainingMeters, let minutes = progress.remainingMinutes else { return nil }
        return DriveStats(remainingMinutes: minutes, remainingMeters: meters, arrival: Date.now.addingTimeInterval(minutes * 60))
    }

    /// Feeds one location fix (real or simulated).
    func update(with location: CLLocation) {
        lastLocation = location
        let alerts = progress.update(with: location.coordinate)
        if let projected = progress.position {
            let onRoute = projected.offRouteMeters <= Self.snapMeters
            // GPS course is unreliable when slow or missing; the route's own direction stands in for it.
            let courseIsUsable = location.course >= 0 && location.speed >= 2
            let carCoordinate = onRoute ? projected.coordinate : location.coordinate
            car = DriveCar(
                latitude: carCoordinate.latitude,
                longitude: carCoordinate.longitude,
                bearing: courseIsUsable ? location.course : projected.bearing
            )
            if onRoute {
                camera = cameraOnRoute(at: projected)
            } else {
                // Off the route: keep the last heading unless the GPS course is trustworthy, and look ahead of the car.
                let heading = courseIsUsable ? location.course : (camera?.heading ?? projected.bearing)
                let center = RouteTrack.coordinate(from: location.coordinate, meters: Self.centerAheadMeters, bearing: heading)
                camera = DriveCamera(latitude: center.latitude, longitude: center.longitude, heading: heading)
            }
        }
        for alert in alerts {
            announce(alert)
        }
        if progress.status == .arrived, finishTask == nil {
            finishTask = Task {
                try? await Task.sleep(for: .seconds(3))
                isFinished = true
            }
        }
    }

    /// Camera for a car on the route: turned to the route's direction over the next 50 m, looking at the
    /// point 80 m further along it, so the road ahead runs up the middle with the car in the lower third.
    private func cameraOnRoute(at position: RouteTrack.Position) -> DriveCamera {
        let track = progress.track
        let heading = track.smoothedBearing(atDistance: position.distanceAlong, lookAhead: Self.headingLookAheadMeters) ?? position.bearing
        let center = track.position(atDistance: position.distanceAlong + Self.centerAheadMeters)?.coordinate ?? position.coordinate
        return DriveCamera(latitude: center.latitude, longitude: center.longitude, heading: heading)
    }

    /// A rerouted result arrived: follow it from here.
    func replaceRoute(_ route: Route) {
        self.route = route
        progress.replaceRoute(route)
        if let lastLocation {
            update(with: lastLocation)
        }
    }

    func toggleMute() {
        isMuted.toggle()
        speaker.isMuted = isMuted
        if isMuted {
            speaker.stop()
        }
    }

    /// Stops speech, the simulator and timers. Call when leaving drive mode.
    func end() {
        simulationTask?.cancel()
        finishTask?.cancel()
        speaker.stop()
    }

    private func announce(_ alert: DriveProgress.Alert) {
        if alert == .offRoute {
            // One request (and one spoken warning) per interval; the banner shows "Off route" regardless.
            guard lastRerouteAt.map({ Date.now.timeIntervalSince($0) > Self.rerouteInterval }) ?? true else { return }
            lastRerouteAt = .now
            rerouteRequests += 1
        }
        alertCount += 1
        speaker.speak(DriveFormat.phrase(for: alert))
    }
}
