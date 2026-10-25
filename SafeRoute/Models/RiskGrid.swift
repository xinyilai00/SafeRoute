//
//  RiskGrid.swift
//  SafeRoute
//

import CoreLocation
import Foundation

/// GET /risk payload: a GeoJSON FeatureCollection of 200 m cells with `properties.risk` in 0...1.
/// Only the keys the app needs are decoded; everything else in the GeoJSON is ignored.
nonisolated struct RiskFeatureCollection: Decodable {
    let features: [RiskFeature]

    /// Drawable cells. GeoJSON coordinates are `[lng, lat]`; this flips them.
    var cells: [RiskCell] {
        var cells: [RiskCell] = []
        for feature in features {
            let rings = feature.geometry.outerRings
            for ring in rings {
                let coordinates = ring.compactMap { point -> CLLocationCoordinate2D? in
                    guard point.count >= 2 else { return nil }
                    return CLLocationCoordinate2D(latitude: point[1], longitude: point[0])
                }
                guard coordinates.count >= 3 else { continue }
                // Grid indices only make sense for a plain single-ring cell.
                let isSingleCell = rings.count == 1
                cells.append(RiskCell(
                    id: cells.count,
                    risk: feature.properties.risk,
                    coordinates: coordinates,
                    ix: isSingleCell ? feature.properties.ix : nil,
                    iy: isSingleCell ? feature.properties.iy : nil
                ))
            }
        }
        return cells
    }
}

nonisolated struct RiskFeature: Decodable {
    let properties: RiskProperties
    let geometry: RiskGeometry
}

nonisolated struct RiskProperties: Decodable {
    let risk: Double
    /// Grid column/row of the cell (x east, y north). Not part of the contract, so optional;
    /// when present, adjacent cells of the same band are merged into one polygon.
    let ix: Int?
    let iy: Int?
}

/// Polygon or MultiPolygon geometry reduced to its outer rings (holes are dropped).
nonisolated struct RiskGeometry: Decodable {
    let type: String
    /// One outer ring per polygon, each a list of `[lng, lat]` points.
    let outerRings: [[[Double]]]

    private enum CodingKeys: String, CodingKey {
        case type, coordinates
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        switch type {
        case "Polygon":
            let rings = try container.decode([[[Double]]].self, forKey: .coordinates)
            outerRings = rings.first.map { [$0] } ?? []
        case "MultiPolygon":
            let polygons = try container.decode([[[[Double]]]].self, forKey: .coordinates)
            outerRings = polygons.compactMap(\.first)
        default:
            outerRings = []
        }
    }
}

/// One decoded grid cell.
nonisolated struct RiskCell: Identifiable {
    let id: Int
    /// 0...1, higher is riskier.
    let risk: Double
    let coordinates: [CLLocationCoordinate2D]
    let ix: Int?
    let iy: Int?
}

/// One smooth heat zone: an outer ring plus any holes (pockets below the band's threshold), in draw order.
nonisolated struct HeatZone: Identifiable {
    let id: Int
    let outer: [CLLocationCoordinate2D]
    let holes: [[CLLocationCoordinate2D]]

    var pointCount: Int { outer.count + holes.reduce(0) { $0 + $1.count } }
}

/// All zones that share one color. Bands are nested: band k holds every cell at or above its threshold,
/// so drawing them lowest to highest stacks translucent layers into a gradient that is hottest in the middle.
nonisolated struct HeatBand: Identifiable {
    /// 0 is the lowest-risk band drawn.
    let level: Int
    /// Position of the band's midpoint in the drawn range, 0...1. Drives the color.
    let midpoint: Double
    let zones: [HeatZone]

    var id: Int { level }
    var pointCount: Int { zones.reduce(0) { $0 + $1.pointCount } }
}

/// Turns decoded cells into a handful of smooth, nested heat zones so the map stays smooth.
/// Computed once per launch, off the main actor (see `RiskService`).
nonisolated enum RiskHeatmap {
    /// Nested bands between `minimum` and 1. Five is the ceiling for smooth panning: every band adds its
    /// zones as MapKit overlays, and ten (1516 overlays) stuttered when zoomed out on device.
    static let bandCount = 5
    /// Rounds of Chaikin corner cutting on each outline; three turn a cell corner into an 8-point arc.
    static let smoothingRounds = 3
    /// Bridge one-cell gaps and notches between hot cells (a 3×3 morphological closing) before outlining, so
    /// near neighbours form one zone; lone cells stay single. On the live grid this cuts the zone count by a third.
    static let bridgesGaps = true

    /// For each of `bandCount` thresholds over `minimum`...1, takes every cell at or above it, traces the
    /// combined outline of those cells on the ix/iy grid (outer rings and holes), and rounds the corners.
    static func bands(from cells: [RiskCell], minimum: Double, bandCount: Int = bandCount) -> [HeatBand] {
        let span = max(1 - minimum, 0.01)
        let grid = Grid(cells: cells)
        var nextID = 0
        var bands: [HeatBand] = []
        for level in 0..<bandCount {
            let threshold = minimum + Double(level) * span / Double(bandCount) - 1e-9
            var members = Set(grid.risk.filter { $0.value >= threshold }.keys)
            if bridgesGaps {
                members = Grid.closed(members)
            }
            var zones: [HeatZone] = []
            for component in grid.components(of: members) {
                for traced in grid.trace(component) {
                    zones.append(HeatZone(id: nextID, outer: smooth(traced.outer), holes: traced.holes.map(smooth)))
                    nextID += 1
                }
            }
            // Cells the server sent without grid indices cannot join an outline; they stay as they are.
            for cell in grid.loose where cell.risk >= threshold {
                zones.append(HeatZone(id: nextID, outer: cell.coordinates, holes: []))
                nextID += 1
            }
            guard !zones.isEmpty else { continue }
            bands.append(HeatBand(level: level, midpoint: (Double(level) + 0.5) / Double(bandCount), zones: zones))
        }
        return bands
    }

    // MARK: - Grid

    /// Integer grid position; for cells it names the cell, for vertices the corner shared by up to four cells
    /// (cell (x, y) spans vertices x...x+1 and y...y+1, with x growing east and y growing north).
    private struct Key: Hashable {
        let x: Int
        let y: Int
    }

    private struct Ring {
        var vertices: [Key]
        /// Shoelace area in grid units; positive means counterclockwise, which is how outer rings are traced.
        var signedArea: Double {
            var sum = 0.0
            for i in vertices.indices {
                let a = vertices[i], b = vertices[(i + 1) % vertices.count]
                sum += Double(a.x * b.y - b.x * a.y)
            }
            return sum / 2
        }
    }

    private struct Traced {
        let outer: [CLLocationCoordinate2D]
        let holes: [[CLLocationCoordinate2D]]
    }

    private struct Grid {
        /// Risk per indexed cell.
        private(set) var risk: [Key: Double] = [:]
        /// Coordinate of each grid vertex, gathered from the cells' corners.
        private var vertices: [Key: CLLocationCoordinate2D] = [:]
        /// Cells without usable indices.
        private(set) var loose: [RiskCell] = []
        /// One known vertex and the grid step, for the rare vertex no fetched cell touches (a bridged gap's corner).
        private var origin: (key: Key, coordinate: CLLocationCoordinate2D)?
        private var stepLongitude = 0.0
        private var stepLatitude = 0.0

        init(cells: [RiskCell]) {
            // The server's index directions are not part of the contract: read them off the data.
            var centers: [Key: CLLocationCoordinate2D] = [:]
            for cell in cells {
                if let ix = cell.ix, let iy = cell.iy, let corners = RiskHeatmap.corners(of: cell.coordinates) {
                    centers[Key(x: ix, y: iy)] = CLLocationCoordinate2D(
                        latitude: (corners.sw.latitude + corners.ne.latitude) / 2,
                        longitude: (corners.sw.longitude + corners.ne.longitude) / 2
                    )
                }
            }
            var xSign = 1, ySign = 1
            for (key, center) in centers {
                if xSign == 1, let east = centers[Key(x: key.x + 1, y: key.y)], east.longitude < center.longitude { xSign = -1 }
                if ySign == 1, let north = centers[Key(x: key.x, y: key.y + 1)], north.latitude < center.latitude { ySign = -1 }
            }

            for cell in cells {
                guard let ix = cell.ix, let iy = cell.iy, let corners = RiskHeatmap.corners(of: cell.coordinates) else {
                    loose.append(cell)
                    continue
                }
                let x = ix * xSign, y = iy * ySign
                risk[Key(x: x, y: y)] = cell.risk
                vertices[Key(x: x, y: y)] = corners.sw
                vertices[Key(x: x + 1, y: y)] = corners.se
                vertices[Key(x: x + 1, y: y + 1)] = corners.ne
                vertices[Key(x: x, y: y + 1)] = corners.nw
                if origin == nil {
                    origin = (Key(x: x, y: y), corners.sw)
                    stepLongitude = corners.se.longitude - corners.sw.longitude
                    stepLatitude = corners.nw.latitude - corners.sw.latitude
                }
            }
        }

        /// Morphological closing with a 3×3 window: dilate, then erode. Fills single-cell gaps, notches and
        /// holes between members without growing isolated cells. The result always contains `members`.
        static func closed(_ members: Set<Key>) -> Set<Key> {
            var dilated = members
            for key in members {
                for dx in -1...1 {
                    for dy in -1...1 {
                        dilated.insert(Key(x: key.x + dx, y: key.y + dy))
                    }
                }
            }
            var result: Set<Key> = []
            for key in dilated {
                var surrounded = true
                search: for dx in -1...1 {
                    for dy in -1...1 where !dilated.contains(Key(x: key.x + dx, y: key.y + dy)) {
                        surrounded = false
                        break search
                    }
                }
                if surrounded {
                    result.insert(key)
                }
            }
            return result
        }

        /// 4-connected groups of `members`.
        func components(of members: Set<Key>) -> [Set<Key>] {
            var remaining = members
            var result: [Set<Key>] = []
            while let seed = remaining.first {
                var component: Set<Key> = []
                var stack = [seed]
                remaining.remove(seed)
                while let key = stack.popLast() {
                    component.insert(key)
                    for next in [Key(x: key.x + 1, y: key.y), Key(x: key.x - 1, y: key.y),
                                 Key(x: key.x, y: key.y + 1), Key(x: key.x, y: key.y - 1)] where remaining.contains(next) {
                        remaining.remove(next)
                        stack.append(next)
                    }
                }
                result.append(component)
            }
            return result
        }

        /// Outlines one component: its boundary edges (each directed with the cells on the left, so outer
        /// rings run counterclockwise and holes clockwise) linked into closed rings, holes matched to the
        /// outer ring around them, and every vertex turned into a coordinate.
        func trace(_ component: Set<Key>) -> [Traced] {
            var outgoing: [Key: [Key]] = [:]
            for cell in component {
                let sw = Key(x: cell.x, y: cell.y), se = Key(x: cell.x + 1, y: cell.y)
                let ne = Key(x: cell.x + 1, y: cell.y + 1), nw = Key(x: cell.x, y: cell.y + 1)
                if !component.contains(Key(x: cell.x, y: cell.y - 1)) { outgoing[sw, default: []].append(se) }
                if !component.contains(Key(x: cell.x + 1, y: cell.y)) { outgoing[se, default: []].append(ne) }
                if !component.contains(Key(x: cell.x, y: cell.y + 1)) { outgoing[ne, default: []].append(nw) }
                if !component.contains(Key(x: cell.x - 1, y: cell.y)) { outgoing[nw, default: []].append(sw) }
            }

            var rings: [Ring] = []
            while let start = outgoing.keys.first(where: { !(outgoing[$0]?.isEmpty ?? true) }) {
                var ring: [Key] = []
                var current = start
                var previous: Key?
                repeat {
                    guard var options = outgoing[current], !options.isEmpty else { break }
                    var choice = options[0]
                    if options.count > 1, let previous {
                        // Two cells touching only at this corner: turn left to stay around the cell we came along,
                        // so each cell keeps its own ring instead of the two fusing through a single vertex.
                        let dx = current.x - previous.x, dy = current.y - previous.y
                        let left = Key(x: current.x - dy, y: current.y + dx)
                        let straight = Key(x: current.x + dx, y: current.y + dy)
                        choice = options.first(where: { $0 == left }) ?? options.first(where: { $0 == straight }) ?? options[0]
                    }
                    options.removeAll { $0 == choice }
                    outgoing[current] = options
                    ring.append(current)
                    previous = current
                    current = choice
                } while current != start
                if ring.count >= 4 {
                    rings.append(Ring(vertices: ring))
                }
            }

            let outers = rings.filter { $0.signedArea > 0 }
            let holes = rings.filter { $0.signedArea < 0 }
            guard !outers.isEmpty else { return [] }
            var holesByOuter = Array(repeating: [Ring](), count: outers.count)
            for hole in holes {
                var index = 0
                if outers.count > 1 {
                    // The cell just right of the hole's first edge lies inside the hole; find the outer ring around it.
                    let a = hole.vertices[0], b = hole.vertices[1]
                    let px = Double(a.x + b.x) / 2 + Double(b.y - a.y) / 2
                    let py = Double(a.y + b.y) / 2 - Double(b.x - a.x) / 2
                    index = outers.firstIndex(where: { RiskHeatmap.contains($0, x: px, y: py) }) ?? 0
                }
                holesByOuter[index].append(hole)
            }
            return outers.indices.compactMap { index in
                guard let outer = coordinates(of: outers[index]) else { return nil }
                return Traced(outer: outer, holes: holesByOuter[index].compactMap(coordinates(of:)))
            }
        }

        private func coordinates(of ring: Ring) -> [CLLocationCoordinate2D]? {
            var result: [CLLocationCoordinate2D] = []
            result.reserveCapacity(ring.vertices.count)
            for vertex in ring.vertices {
                if let coordinate = vertices[vertex] {
                    result.append(coordinate)
                } else if let origin {
                    // A bridged cell's corner that no fetched cell shares: place it on the regular grid.
                    result.append(CLLocationCoordinate2D(
                        latitude: origin.coordinate.latitude + Double(vertex.y - origin.key.y) * stepLatitude,
                        longitude: origin.coordinate.longitude + Double(vertex.x - origin.key.x) * stepLongitude
                    ))
                } else {
                    return nil
                }
            }
            return result
        }
    }

    /// Ray-casting point-in-polygon in grid units.
    private static func contains(_ ring: Ring, x: Double, y: Double) -> Bool {
        var inside = false
        let points = ring.vertices
        var j = points.count - 1
        for i in points.indices {
            let xi = Double(points[i].x), yi = Double(points[i].y)
            let xj = Double(points[j].x), yj = Double(points[j].y)
            if (yi > y) != (yj > y), x < (xj - xi) * (y - yi) / (yj - yi) + xi {
                inside.toggle()
            }
            j = i
        }
        return inside
    }

    // MARK: - Smoothing

    /// Chaikin corner cutting on a closed ring (each edge is replaced by its 1/4 and 3/4 points), then the
    /// points that still lie on a straight run are dropped, so long edges cost two points and corners eight.
    static func smooth(_ ring: [CLLocationCoordinate2D]) -> [CLLocationCoordinate2D] {
        guard ring.count >= 3 else { return ring }
        var points = ring.map { (x: $0.longitude, y: $0.latitude) }
        for _ in 0..<smoothingRounds {
            var next: [(x: Double, y: Double)] = []
            next.reserveCapacity(points.count * 2)
            for i in points.indices {
                let a = points[i], b = points[(i + 1) % points.count]
                next.append((x: 0.75 * a.x + 0.25 * b.x, y: 0.75 * a.y + 0.25 * b.y))
                next.append((x: 0.25 * a.x + 0.75 * b.x, y: 0.25 * a.y + 0.75 * b.y))
            }
            points = next
        }
        var kept: [CLLocationCoordinate2D] = []
        let count = points.count
        for i in 0..<count {
            let p = points[(i + count - 1) % count], q = points[i], r = points[(i + 1) % count]
            let cross = (q.x - p.x) * (r.y - q.y) - (q.y - p.y) * (r.x - q.x)
            if abs(cross) > 1e-14 {
                kept.append(CLLocationCoordinate2D(latitude: q.y, longitude: q.x))
            }
        }
        return kept.count >= 3 ? kept : ring
    }

    // MARK: - Cell corners

    private struct Corners {
        let sw: CLLocationCoordinate2D
        let se: CLLocationCoordinate2D
        let ne: CLLocationCoordinate2D
        let nw: CLLocationCoordinate2D
    }

    /// Classifies a 4-corner ring (optionally closed) into compass corners. Nil if it is not a simple quad.
    private static func corners(of ring: [CLLocationCoordinate2D]) -> Corners? {
        var points = ring
        if points.count == 5, let first = points.first, let last = points.last,
           first.latitude == last.latitude, first.longitude == last.longitude {
            points.removeLast()
        }
        guard points.count == 4 else { return nil }
        let centerLat = points.map(\.latitude).reduce(0, +) / 4
        let centerLon = points.map(\.longitude).reduce(0, +) / 4
        var sw: CLLocationCoordinate2D?, se: CLLocationCoordinate2D?
        var ne: CLLocationCoordinate2D?, nw: CLLocationCoordinate2D?
        for point in points {
            switch (point.latitude >= centerLat, point.longitude >= centerLon) {
            case (false, false): sw = point
            case (false, true): se = point
            case (true, true): ne = point
            case (true, false): nw = point
            }
        }
        guard let sw, let se, let ne, let nw else { return nil }
        return Corners(sw: sw, se: se, ne: ne, nw: nw)
    }
}
