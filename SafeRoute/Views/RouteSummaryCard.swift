//
//  RouteSummaryCard.swift
//  SafeRoute
//

import SwiftUI

/// Liquid Glass route card, sheet-like: a grabber, a hero row for the safe route (ETA and arrival time on
/// the left, "23% safer" pill and distance on the right), the quicker route under a divider, one amber
/// line of what the safe route avoids, the backend's notes only when present, and a full-width Start.
/// Dragging or flicking it down dismisses the route. Type stays large because elderly drivers are a target user.
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
    /// Called when the card is dragged or flicked down far enough. Nil disables the gesture (drive mode).
    var onDismiss: (() -> Void)?

    /// Set when the long press fires so the button's own action (on release) does not also start a real drive.
    @State private var didLongPress = false
    /// How far the card has been pulled down, while the finger is on it.
    @State private var dragOffset: CGFloat = 0

    /// Drags past this dismiss; shorter ones spring back.
    private static let dismissDragDistance: CGFloat = 90
    /// A flick: where the drag would have ended on its own.
    private static let dismissFlickDistance: CGFloat = 180

    /// A little darker than the system green so white and green text read well, which matters for elderly drivers.
    private static let deepGreen = Color(red: 0.12, green: 0.60, blue: 0.32)

    private var response: RouteResponse { result.response }
    private var safest: Route { response.safest }
    private var fastest: Route { response.fastest }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            grabber
            VStack(alignment: .leading, spacing: 12) {
                heroRow
                Divider()
                if response.routesAreIdentical {
                    headsUpLine
                } else {
                    quickerRouteRow
                }
                notes
            }
            .opacity(isReloading ? 0.55 : 1)
            .animation(.easeInOut(duration: 0.2), value: isReloading)
            startButton
                .padding(.top, 16)
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        .padding(.top, 8)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        // The whole card is a drag target, including the glass between elements and around the grabber;
        // without this only the text, shapes and buttons would catch touches and the map would pan instead.
        .contentShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .offset(y: dragOffset)
        .gesture(dismissGesture, including: onDismiss == nil ? .subviews : .all)
        .accessibilityAction(named: "Dismiss route") { onDismiss?() }
    }

    // MARK: - Grabber and dismissal

    private var grabber: some View {
        Capsule()
            .fill(.secondary.opacity(0.5))
            .frame(width: 40, height: 5)
            .frame(maxWidth: .infinity)
            .padding(.bottom, 12)
            .accessibilityHidden(true)
    }

    private var dismissGesture: some Gesture {
        DragGesture(minimumDistance: 12, coordinateSpace: .local)
            .onChanged { value in
                // Only follow downward pulls; an upward drag does nothing.
                dragOffset = max(0, value.translation.height)
            }
            .onEnded { value in
                let pulledFarEnough = value.translation.height > Self.dismissDragDistance
                let flicked = value.predictedEndTranslation.height > Self.dismissFlickDistance
                if let onDismiss, pulledFarEnough || flicked {
                    onDismiss()
                } else {
                    withAnimation(.spring(duration: 0.35, bounce: 0.2)) {
                        dragOffset = 0
                    }
                }
            }
    }

    // MARK: - Hero row

    /// Safe route: ETA and arrival time on the left in deep green; the safer pill and the distance on the right.
    /// Two rows, so the pill is centered on the ETA digits and the distance shares the arrival line's baseline.
    private var heroRow: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center, spacing: 12) {
                Text("\(displayedMinutes(safest)) min")
                    .font(.system(size: 44, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(Self.deepGreen)
                    .fixedSize()
                Spacer(minLength: 8)
                Text(response.routesAreIdentical ? "Safest and fastest" : "\(riskPercent)% safer")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Self.deepGreen, in: Capsule())
                    .fixedSize()
            }
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                // Re-rendered every minute so a card left open does not promise a stale arrival time.
                TimelineView(.everyMinute) { context in
                    Text("Arrive \(context.date.addingTimeInterval(safest.etaMinutes * 60).formatted(date: .omitted, time: .shortened))")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Self.deepGreen)
                        .fixedSize()
                }
                Spacer(minLength: 8)
                Text(miles(safest))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize()
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var riskPercent: Int {
        max(0, Int(response.comparison.riskReductionPct.rounded()))
    }

    // MARK: - Quicker route and hazards

    /// The fastest route in gray, then the amber line of what the safe route avoids (when anything).
    @ViewBuilder
    private var quickerRouteRow: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text("\(displayedMinutes(fastest)) min")
                    .font(.title2.weight(.medium))
                    .monospacedDigit()
                    .foregroundStyle(.gray)
                    .fixedSize()
                Text("Quicker route · \(miles(fastest))")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
            if !response.avoidedHazards.isEmpty {
                hazardText(response.avoidedHazards)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Avoids " + response.avoidedHazards.map(\.text).joined(separator: ", "))
            }
        }
    }

    /// Identical routes: the maneuver hazards still on the route, or a reassurance when there are none.
    @ViewBuilder
    private var headsUpLine: some View {
        let hazards = safest.maneuverHazardCounts
        if hazards.isEmpty {
            Text("No risky merges or busy left turns")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            Text("Heads up: \(hazardText(hazards))")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel("Heads up: " + hazards.map(\.text).joined(separator: ", "))
        }
    }

    /// "⤴ 2 highway merges · ⚠ 1 crash hotspot": one sentence-like line that wraps naturally.
    /// Built with Text interpolation (Text and Image both interpolate), since `+` on Text is deprecated in iOS 26.
    private func hazardText(_ hazards: [HazardCount]) -> Text {
        var line: Text?
        for hazard in hazards {
            let piece = Text("\(Image(systemName: hazard.kind.symbolName)) \(hazard.text)")
            line = line.map { Text("\($0) · \(piece)") } ?? piece
        }
        return line ?? Text("")
    }

    // MARK: - Notes

    /// Closure and avoid information from the backend, one line each and only when present,
    /// plus a small tag when the mock data was used.
    @ViewBuilder
    private var notes: some View {
        if let note = result.closureNote {
            noteLine(note.text, symbol: note.symbolName, color: note == .crosses ? .orange : Self.deepGreen)
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

    /// Full-width deep green button. Tap starts a real drive (or the simulation, for a preview);
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
            Label(isPreview ? "Preview" : "Start", systemImage: "car.fill")
                .font(.title3.weight(.bold))
        }
        .buttonStyle(StartButtonStyle(fill: Self.deepGreen))
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

    /// Whole minutes as displayed.
    private func displayedMinutes(_ route: Route) -> Int {
        Int(route.etaMinutes.rounded())
    }

    private func miles(_ route: Route) -> String {
        String(format: "%.1f mi", route.distanceMiles)
    }
}

/// Full-width solid block with white content, dimming while pressed.
private struct StartButtonStyle: ButtonStyle {
    let fill: Color

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
        return configuration.label
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 56)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: shape)
            .contentShape(shape)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
