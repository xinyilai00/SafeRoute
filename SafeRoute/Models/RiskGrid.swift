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

/// One polygon to draw with `MapPolygon`: a single cell, or a rectangle of merged same-band cells.
nonisolated struct HeatPolygon: Identifiable {
    let id: Int
    let coordinates: [CLLocationCoordinate2D]
}

/// All polygons that share one color.
nonisolated struct HeatBand: Identifiable {
    /// 0 is the lowest-risk band drawn.
    let level: Int
    /// Position of the band's midpoint in the drawn range, 0...1. Drives the color.
    let midpoint: Double
    let polygons: [HeatPolygon]

    var id: Int { level }
}

/// Turns decoded cells into a small number of banded, merged polygons so the map stays smooth.
nonisolated enum RiskHeatmap {
    static let bandCount = 5

    /// Buckets `cells` into `bandCount` risk bands over `minimum`...1 and merges neighbouring cells
    /// of the same band into rectangles. Computed once per launch.
    static func bands(from cells: [RiskCell], minimum: Double, bandCount: Int = bandCount) -> [HeatBand] {
        let span = max(1 - minimum, 0.01)
        var grouped = Array(repeating: [RiskCell](), count: bandCount)
        for cell in cells {
            let t = min(max((cell.risk - minimum) / span, 0), 1)
            let level = min(Int(t * Double(bandCount)), bandCount - 1)
            grouped[level].append(cell)
        }

        var nextID = 0
        return grouped.enumerated().compactMap { level, cells in
            guard !cells.isEmpty else { return nil }
            let polygons = mergedRings(cells).map { ring in
                defer { nextID += 1 }
                return HeatPolygon(id: nextID, coordinates: ring)
            }
            return HeatBand(level: level, midpoint: (Double(level) + 0.5) / Double(bandCount), polygons: polygons)
        }
    }

    // MARK: - Merging

    private struct GridKey: Hashable {
        let ix: Int
        let iy: Int
    }

    private struct Corners {
        let sw: CLLocationCoordinate2D
        let se: CLLocationCoordinate2D
        let ne: CLLocationCoordinate2D
        let nw: CLLocationCoordinate2D
    }

    private struct Rect {
        var ixStart: Int
        var ixEnd: Int
        var iyStart: Int
        var iyEnd: Int
    }

    private struct Span: Hashable {
        let ixStart: Int
        let ixEnd: Int
    }

    /// Cells with grid indices and four classifiable corners are merged: first into horizontal runs,
    /// then runs with the same x-range stacked vertically into rectangles. Anything else is kept as-is.
    static func mergedRings(_ cells: [RiskCell]) -> [[CLLocationCoordinate2D]] {
        var rings: [[CLLocationCoordinate2D]] = []
        var grid: [GridKey: Corners] = [:]
        for cell in cells {
            if let ix = cell.ix, let iy = cell.iy, let corners = corners(of: cell.coordinates) {
                grid[GridKey(ix: ix, iy: iy)] = corners
            } else {
                rings.append(cell.coordinates)
            }
        }

        // 1. Horizontal runs of consecutive ix within each row.
        var strips: [(iy: Int, span: Span)] = []
        let rows = Dictionary(grouping: grid.keys, by: \.iy)
        for iy in rows.keys.sorted() {
            let xs = rows[iy]!.map(\.ix).sorted()
            var start = xs[0]
            var previous = xs[0]
            for x in xs.dropFirst() {
                if x == previous + 1 {
                    previous = x
                } else {
                    strips.append((iy, Span(ixStart: start, ixEnd: previous)))
                    start = x
                    previous = x
                }
            }
            strips.append((iy, Span(ixStart: start, ixEnd: previous)))
        }

        // 2. Stack runs with an identical x-range on consecutive rows.
        var rects: [Rect] = []
        let columns = Dictionary(grouping: strips, by: \.span)
        for span in columns.keys.sorted(by: { ($0.ixStart, $0.ixEnd) < ($1.ixStart, $1.ixEnd) }) {
            let ys = columns[span]!.map(\.iy).sorted()
            var current = Rect(ixStart: span.ixStart, ixEnd: span.ixEnd, iyStart: ys[0], iyEnd: ys[0])
            for y in ys.dropFirst() {
                if y == current.iyEnd + 1 {
                    current.iyEnd = y
                } else {
                    rects.append(current)
                    current = Rect(ixStart: span.ixStart, ixEnd: span.ixEnd, iyStart: y, iyEnd: y)
                }
            }
            rects.append(current)
        }

        // 3. Outline each rectangle from the corner cells.
        for rect in rects {
            guard let sw = grid[GridKey(ix: rect.ixStart, iy: rect.iyStart)]?.sw,
                  let se = grid[GridKey(ix: rect.ixEnd, iy: rect.iyStart)]?.se,
                  let ne = grid[GridKey(ix: rect.ixEnd, iy: rect.iyEnd)]?.ne,
                  let nw = grid[GridKey(ix: rect.ixStart, iy: rect.iyEnd)]?.nw else { continue }
            rings.append([sw, se, ne, nw])
        }
        return rings
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
