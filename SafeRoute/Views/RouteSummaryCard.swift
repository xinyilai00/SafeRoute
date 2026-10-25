//
//  RouteSummaryCard.swift
//  SafeRoute
//

import SwiftUI

/// Compact Liquid Glass card: the safe route (with Start beside it) over the fastest route, one scrolling
/// row of what the safe route avoids, and the backend's closure / avoid notes only when it sent any.
/// Type stays large because elderly drivers are a target user.
struct RouteSummaryCard: View {
    let result: RouteResult
    /// True while a new request (e.g. after a profile change) is replacing this result.
    var isReloading = false
    /// Tapping Start begins drive mode along the safe route.
    var onStart: () -> Void = {}
    /// Holding Start begins a simulated demo drive instead.
    var onSimulate: () -> Void = {}
    /// True when the route does not start at the user's location: the button reads "Preview" and
    /// a tap runs the simulated drive, since a real one could not be followed from here.
    var isPreview = false

    /// Set when the long press fires so the button's own action (on release) does not also start a real drive.
    @State private var didLongPress = false

    private var response: RouteResponse { result.response }
    private var safest: Route { response.safest }
    private var fastest: Route { response.fastest }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    safeRouteRow
                    if !response.routesAreIdentical {
                        fastestRouteRow
                    }
                }
                Spacer(minLength: 8)
                startButton
            }

            if response.routesAreIdentical {
                headsUpRow
            } else if !response.avoidedHazards.isEmpty {
                chipRow(label: "Avoids", hazards: response.avoidedHazards, tint: .green)
            }

            notes
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    // MARK: - Route rows

    /// Green dot, ETA, distance, and the risk saving (or "Also the safest route" when the routes match).
    private var safeRouteRow: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            dot(.green, size: 12, lift: 2)
            Text("\(displayedMinutes(safest)) min")
                .font(.title.weight(.bold))
                .monospacedDigit()
            Text(miles(safest))
                .font(.body)
                .foregroundStyle(.secondary)
            Text(response.routesAreIdentical ? "Also the safest route" : riskText)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(response.routesAreIdentical || riskPercent >= 1 ? .green : .secondary)
            if isReloading {
                ProgressView()
                    .controlSize(.small)
            }
        }
        .lineLimit(1)
        .minimumScaleFactor(0.8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "Safe route: \(displayedMinutes(safest)) minutes, \(miles(safest)), "
            + (response.routesAreIdentical ? "also the safest route" : riskText)
        )
    }

    /// Gray dot, ETA, distance, and how much time it saves, in neutral text (it is never the recommendation).
    private var fastestRouteRow: some View {
        let saved = displayedMinutes(safest) - displayedMinutes(fastest)
        let savedText = saved >= 1 ? "\(saved) min faster" : "Same time"
        return HStack(alignment: .firstTextBaseline, spacing: 8) {
            dot(.gray, size: 10, lift: 0)
            Text("\(displayedMinutes(fastest)) min")
                .font(.title3.weight(.semibold))
                .monospacedDigit()
            Text(miles(fastest))
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(savedText)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .lineLimit(1)
        .minimumScaleFactor(0.8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "Fastest route: \(displayedMinutes(fastest)) minutes, \(miles(fastest)), "
            + (saved >= 1 ? "\(saved) minutes faster" : "same time")
        )
    }

    /// Route dot aligned to the text baseline, lifted so it sits on the lower-case height of its row.
    private func dot(_ color: Color, size: CGFloat, lift: CGFloat) -> some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .alignmentGuide(.firstTextBaseline) { dimensions in dimensions[.bottom] + lift }
            .accessibilityHidden(true)
    }

    private var riskPercent: Int { Int(response.comparison.riskReductionPct.rounded()) }

    private var riskText: String {
        riskPercent >= 1 ? "\(riskPercent)% less risk" : "Similar risk"
    }

    // MARK: - Chips

    /// One scrolling row: a short lead-in word, then a capsule per hazard type. The row runs edge to edge
    /// of the card so chips scroll out under its padding instead of being cut mid-card.
    private func chipRow(label: String, hazards: [HazardCount], tint: Color) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Text(label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(hazards) { hazard in
                    Label(hazard.text, systemImage: hazard.kind.symbolName)
                        .font(.subheadline.weight(.medium))
                        .lineLimit(1)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(tint.opacity(0.14), in: Capsule())
                }
            }
            .padding(.horizontal, 16)
        }
        .padding(.horizontal, -16)
    }

    /// Identical routes: the maneuver hazards on the one route, or a reassurance when there are none.
    @ViewBuilder
    private var headsUpRow: some View {
        let hazards = safest.maneuverHazardCounts
        if hazards.isEmpty {
            noteLine("No risky merges or busy left turns on this route", symbol: "checkmark.circle.fill", color: .green)
        } else {
            chipRow(label: "Heads up", hazards: hazards, tint: .orange)
        }
    }

    // MARK: - Notes

    /// Closure and avoid information from the backend, one line each and only when present,
    /// plus a small tag when the mock data was used.
    @ViewBuilder
    private var notes: some View {
        if let note = result.closureNote {
            noteLine(note.text, symbol: note.symbolName, color: note == .crosses ? .orange : .green)
        }
        if let avoided = result.avoidApplied.listText {
            noteLine("Avoiding \(avoided)", symbol: "slider.horizontal.3", color: .secondary)
        }
        if let note = result.avoidNote {
            noteLine(note, symbol: "exclamationmark.triangle.fill", color: .orange)
        }
        if result.isDemoData {
            Text("Demo data")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(.orange.opacity(0.18), in: Capsule())
                .accessibilityLabel("Demo data: the backend was not reachable")
        }
    }

    private func noteLine(_ text: String, symbol: String, color: Color) -> some View {
        Label(text, systemImage: symbol)
            .font(.footnote.weight(.medium))
            .foregroundStyle(color)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Start

    /// Tall green button beside the route rows. Tap starts a real drive (or the simulation, for a preview);
    /// a 0.6 s hold always starts the simulated demo.
    private var startButton: some View {
        Button {
            if didLongPress {
                didLongPress = false
            } else if isPreview {
                onSimulate()
            } else {
                onStart()
            }
        } label: {
            VStack(spacing: 4) {
                Image(systemName: isPreview ? "play.fill" : "car.fill")
                    .font(.title2.weight(.bold))
                Text(isPreview ? "Preview" : "Start")
                    .font(.headline.weight(.bold))
            }
            .frame(width: 64, height: 54)
        }
        .buttonStyle(.borderedProminent)
        .buttonBorderShape(.roundedRectangle(radius: 20))
        .tint(.green)
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.6).onEnded { _ in
                didLongPress = true
                onSimulate()
            }
        )
        .accessibilityLabel(isPreview ? "Preview" : "Start")
        .accessibilityHint(isPreview
            ? "Plays a simulated drive along the safe route."
            : "Starts drive mode along the safe route. Hold to run a simulated demo drive.")
    }

    // MARK: - Helpers

    /// Whole minutes as displayed, so the time difference always agrees with the two ETAs.
    private func displayedMinutes(_ route: Route) -> Int {
        Int(route.etaMinutes.rounded())
    }

    private func miles(_ route: Route) -> String {
        String(format: "%.1f mi", route.distanceMiles)
    }
}
