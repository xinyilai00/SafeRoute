//
//  RouteSummaryCard.swift
//  SafeRoute
//

import SwiftUI

/// Compact Liquid Glass card: the safe route over the fastest, two lines each, with Start beside them;
/// then wrapped chips for what the safe route avoids, and the backend's closure / avoid notes only when
/// it sent any. Type stays large because elderly drivers are a target user. Nothing truncates: the ETA
/// lines fall back to stacking when a row would not fit, and chips wrap.
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
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 10) {
                    safeRouteBlock
                    if !response.routesAreIdentical {
                        fastestRouteBlock
                    }
                }
                Spacer(minLength: 8)
                startButton
            }
            // Ideal height only, so the Start button can stretch to the route blocks and no further.
            .fixedSize(horizontal: false, vertical: true)

            if response.routesAreIdentical {
                headsUp
            } else if !response.avoidedHazards.isEmpty {
                chipFlow(label: "Avoids", hazards: response.avoidedHazards, tint: .green)
            }

            notes
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    // MARK: - Route blocks

    /// Line 1: ETA in extra-large bold plus the green "33% safer" capsule. Line 2: "Safe route · 15.8 mi".
    private var safeRouteBlock: some View {
        VStack(alignment: .leading, spacing: 2) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    safeETA
                    saferCapsule
                    reloadIndicator
                }
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        safeETA
                        reloadIndicator
                    }
                    saferCapsule
                }
            }
            Text("\(response.routesAreIdentical ? "Fastest route" : "Safe route") · \(miles(safest))")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var safeETA: some View {
        Text("\(displayedMinutes(safest)) min")
            .font(.largeTitle.weight(.bold))
            .monospacedDigit()
            .fixedSize()
    }

    @ViewBuilder
    private var saferCapsule: some View {
        if let text = saferText {
            Text(text)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(.green, in: Capsule())
                .fixedSize()
        }
    }

    /// "33% safer" from `risk_reduction_pct`; "Also the safest" when the routes match; nil if there is no saving to claim.
    private var saferText: String? {
        if response.routesAreIdentical { return "Also the safest" }
        let percent = Int(response.comparison.riskReductionPct.rounded())
        return percent >= 1 ? "\(percent)% safer" : nil
    }

    @ViewBuilder
    private var reloadIndicator: some View {
        if isReloading {
            ProgressView()
                .controlSize(.small)
        }
    }

    /// Line 1: ETA large but lighter plus "7 min faster" in secondary. Line 2: "Fastest route · 17.4 mi". Never green.
    private var fastestRouteBlock: some View {
        let saved = displayedMinutes(safest) - displayedMinutes(fastest)
        let fastETA = Text("\(displayedMinutes(fastest)) min")
            .font(.title2.weight(.regular))
            .monospacedDigit()
            .fixedSize()
        let savedText = Text(saved >= 1 ? "\(saved) min faster" : "Same time")
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .fixedSize()
        return VStack(alignment: .leading, spacing: 2) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    fastETA
                    savedText
                }
                VStack(alignment: .leading, spacing: 2) {
                    fastETA
                    savedText
                }
            }
            Text("Fastest route · \(miles(fastest))")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: - Chips

    /// A lead-in word then a capsule per hazard type, wrapping onto as many lines as needed.
    private func chipFlow(label: String, hazards: [HazardCount], tint: Color) -> some View {
        FlowLayout(spacing: 8, rowSpacing: 8) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(hazards) { hazard in
                Label(hazard.text, systemImage: hazard.kind.symbolName)
                    .font(.subheadline.weight(.medium))
                    .fixedSize()
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(tint.opacity(0.14), in: Capsule())
            }
        }
    }

    /// Identical routes: the maneuver hazards on the one route, or a reassurance when there are none.
    @ViewBuilder
    private var headsUp: some View {
        let hazards = safest.maneuverHazardCounts
        if hazards.isEmpty {
            noteLine("No risky merges or busy left turns on this route", symbol: "checkmark.circle.fill", color: .green)
        } else {
            chipFlow(label: "Heads up", hazards: hazards, tint: .orange)
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
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Start

    /// Fixed-width green button beside the route blocks, as tall as they are. Tap starts a real drive
    /// (or the simulation, for a preview); a 0.6 s hold always starts the simulated demo.
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
            VStack(spacing: 6) {
                Image(systemName: isPreview ? "play.fill" : "car.fill")
                    .font(.title2.weight(.bold))
                Text(isPreview ? "Preview" : "Start")
                    .font(.headline.weight(.bold))
                    .fixedSize()
            }
        }
        .buttonStyle(StartButtonStyle())
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

/// Solid green block with white content: a fixed width that always fits "Preview", and a height that
/// stretches to whatever the row beside it needs (at least 72 pt).
private struct StartButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        return configuration.label
            .foregroundStyle(.white)
            .frame(width: 92)
            .frame(maxHeight: .infinity)
            .frame(minHeight: 72)
            .background(.green.opacity(configuration.isPressed ? 0.7 : 1), in: shape)
            .contentShape(shape)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
