//
//  RouteTrack.swift
//  SafeRoute
//

import CoreLocation
import MapKit

/// A route's geometry as a measured track: distance along it, nearest-point projection and the
/// direction of travel. Pure geometry, shared by drive mode and the drive simulator.
nonisolated struct RouteTrack {
    let coordinates: [CLLocationCoordinate2D]
    let totalMeters: Double
    private let points: [MKMapPoint]
    /// Meters from the start to each vertex; same count as `points`.
    private let vertexMeters: [Double]
    private let metersPerPoint: Double

    /// A point on the track.
    struct Position: Equatable {
        /// Meters from the start of the route.
        var distanceAlong: Double
        /// How far the original location was from the route.
        var offRouteMeters: Double
        var latitude: Double
        var longitude: Double
        /// Direction of travel along the route here, in degrees clockwise from north.
        var bearing: Double

        var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }
    }

    init(coordinates: [CLLocationCoordinate2D]) {
        self.coordinates = coordinates
        points = coordinates.map(MKMapPoint.init)
        let midLatitude = coordinates.isEmpty ? 0 : coordinates.map(\.latitude).reduce(0, +) / Double(coordinates.count)
        metersPerPoint = MKMetersPerMapPointAtLatitude(midLatitude)

        var meters: [Double] = []
        meters.reserveCapacity(points.count)
        var running = 0.0
        for index in points.indices {
            if index > 0 {
                running += hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y) * metersPerPoint
            }
            meters.append(running)
        }
        vertexMeters = meters
        totalMeters = running
    }

    /// The nearest point on the route to `coordinate`. When `previousDistance` is given, a point at most
    /// 50 m behind it is preferred as long as it is within 75 m of the route, so a route that loops back
    /// near itself does not snap the driver backwards.
    func position(nearest coordinate: CLLocationCoordinate2D, after previousDistance: Double? = nil) -> Position? {
        guard points.count >= 2 else { return nil }
        let p = MKMapPoint(coordinate)
        var best: (index: Int, t: Double, offMeters: Double)?
        var forward: (index: Int, t: Double, offMeters: Double)?

        for index in 0..<(points.count - 1) {
            let a = points[index], b = points[index + 1]
            let dx = b.x - a.x, dy = b.y - a.y
            let lengthSquared = dx * dx + dy * dy
            let t = lengthSquared > 0 ? min(max(((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared, 0), 1) : 0
            let offMeters = hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy)) * metersPerPoint
            if best == nil || offMeters < best!.offMeters {
                best = (index, t, offMeters)
            }
            if let previousDistance, offMeters <= 75 {
                let along = vertexMeters[index] + t * (vertexMeters[index + 1] - vertexMeters[index])
                if along >= previousDistance - 50, forward == nil || offMeters < forward!.offMeters {
                    forward = (index, t, offMeters)
                }
            }
        }
        guard let chosen = forward ?? best else { return nil }
        return position(segment: chosen.index, t: chosen.t, offRouteMeters: chosen.offMeters)
    }

    /// The point `distance` meters from the start (clamped to the route). Used by the simulator.
    func position(atDistance distance: Double) -> Position? {
        guard points.count >= 2 else { return nil }
        let clamped = min(max(distance, 0), totalMeters)
        var index = 0
        while index < points.count - 2, vertexMeters[index + 1] < clamped {
            index += 1
        }
        let segmentMeters = vertexMeters[index + 1] - vertexMeters[index]
        let t = segmentMeters > 0 ? (clamped - vertexMeters[index]) / segmentMeters : 0
        return position(segment: index, t: t, offRouteMeters: 0)
    }

    private func position(segment index: Int, t: Double, offRouteMeters: Double) -> Position {
        let a = points[index], b = points[index + 1]
        let q = MKMapPoint(x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y)).coordinate
        return Position(
            distanceAlong: vertexMeters[index] + t * (vertexMeters[index + 1] - vertexMeters[index]),
            offRouteMeters: offRouteMeters,
            latitude: q.latitude,
            longitude: q.longitude,
            bearing: Self.bearing(from: coordinates[index], to: coordinates[index + 1])
        )
    }

    /// Direction of travel averaged over the next `lookAhead` meters: the bearing from the point at
    /// `distance` to the point `lookAhead` further on (clamped to the end). Unlike the segment bearing it
    /// turns gradually through vertices, so a camera following it does not jerk at every corner.
    func smoothedBearing(atDistance distance: Double, lookAhead: Double) -> Double? {
        guard let from = position(atDistance: distance) else { return nil }
        let aheadDistance = min(from.distanceAlong + lookAhead, totalMeters)
        guard aheadDistance - from.distanceAlong > 1, let to = position(atDistance: aheadDistance) else { return from.bearing }
        return Self.bearing(from: from.coordinate, to: to.coordinate)
    }

    /// The point `meters` away from `origin` in the direction `bearing` (degrees clockwise from north).
    static func coordinate(from origin: CLLocationCoordinate2D, meters: Double, bearing: Double) -> CLLocationCoordinate2D {
        let earthRadius = 6_371_000.0
        let angular = meters / earthRadius
        let heading = bearing * .pi / 180
        let lat1 = origin.latitude * .pi / 180, lon1 = origin.longitude * .pi / 180
        let lat2 = asin(sin(lat1) * cos(angular) + cos(lat1) * sin(angular) * cos(heading))
        let lon2 = lon1 + atan2(sin(heading) * sin(angular) * cos(lat1), cos(angular) - sin(lat1) * sin(lat2))
        return CLLocationCoordinate2D(latitude: lat2 * 180 / .pi, longitude: lon2 * 180 / .pi)
    }

    /// Initial bearing from `a` to `b` in degrees clockwise from north, 0..<360.
    static func bearing(from a: CLLocationCoordinate2D, to b: CLLocationCoordinate2D) -> Double {
        let lat1 = a.latitude * .pi / 180, lat2 = b.latitude * .pi / 180
        let deltaLon = (b.longitude - a.longitude) * .pi / 180
        let y = sin(deltaLon) * cos(lat2)
        let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(deltaLon)
        let degrees = atan2(y, x) * 180 / .pi
        return (degrees + 360).truncatingRemainder(dividingBy: 360)
    }
}
