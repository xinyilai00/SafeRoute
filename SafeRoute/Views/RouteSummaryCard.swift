//
//  RouteSummaryCard.swift
//  SafeRoute
//

import SwiftUI

/// Liquid Glass card explaining, in plain words first, what the safe route avoids.
/// Technical numbers live behind the "Details" disclosure.
struct RouteSummaryCard: View {
    let result: RouteResult
    /// True while a new request (e.g. after a profile change) is replacing this result.
    var isReloading = false

    @State private var showsDetails = false

    private var response: RouteResponse { result.response }
    private var safest: Route { response.safest }
    private var fastest: Route { response.fastest }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if response.routesAreIdentical {
                sameRouteContent
            } else {
                comparisonContent
            }
            details
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    // MARK: - Two different routes

    @ViewBuilder
    private var comparisonContent: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Label("Safer Route", systemImage: "shield.checkered")
                .font(.title3.weight(.bold))
            Spacer(minLength: 8)
            if isReloading {
                ProgressView()
                    .controlSize(.small)
            }
            if result.isLiveTraffic {
                liveTrafficPill
            }
            addedTimeBadge
        }

        Text(response.avoidanceSentence ?? response.comparison.summary)
            .font(.body)
            .fixedSize(horizontal: false, vertical: true)

        closureLine

        VStack(spacing: 10) {
            routeRow(name: "Safe route", color: .green, route: safest)
            routeRow(name: "Fastest route", color: .gray, route: fastest)
        }

        if !response.avoidedHazards.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("What you avoid")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                chips
            }
        }
    }

    private var addedTimeBadge: some View {
        let added = displayedMinutes(safest) - displayedMinutes(fastest)
        return Text(added >= 1 ? "+\(added) min" : "same time")
            .font(.subheadline.weight(.bold))
            .monospacedDigit()
            .foregroundStyle(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(.green, in: Capsule())
            .accessibilityLabel(added >= 1 ? "\(added) minutes added" : "Same time")
    }

    private func routeRow(name: String, color: Color, route: Route) -> some View {
        HStack(spacing: 10) {
            Circle()
                .fill(color)
                .frame(width: 10, height: 10)
            Text(name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color)
            Spacer(minLength: 8)
            Text("\(displayedMinutes(route)) min")
                .font(.title2.weight(.bold))
                .monospacedDigit()
            VStack(alignment: .trailing, spacing: 3) {
                RiskMeter(filled: riskDots(for: route), color: color)
                Text(riskLabel(for: route))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(minWidth: 64, alignment: .trailing)
        }
        .accessibilityElement(children: .combine)
    }

    private var chips: some View {
        chipGrid(response.avoidedHazards, tint: .green)
    }

    private func chipGrid(_ hazards: [HazardCount], tint: Color) -> some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 150), spacing: 8, alignment: .leading)],
            alignment: .leading,
            spacing: 8
        ) {
            ForEach(hazards) { hazard in
                Label(hazard.text, systemImage: hazard.kind.symbolName)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(2)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(tint.opacity(0.14), in: Capsule())
            }
        }
    }

    private var liveTrafficPill: some View {
        Label("Live traffic", systemImage: "dot.radiowaves.left.and.right")
            .font(.caption.weight(.semibold))
            .foregroundStyle(.blue)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.blue.opacity(0.14), in: Capsule())
            .accessibilityLabel("ETAs use live traffic")
    }

    /// Closure information from the backend, when any: a warning if the route crosses one,
    /// a reassurance when closed roads were routed around.
    @ViewBuilder
    private var closureLine: some View {
        if let note = result.closureNote {
            Label(note.text, systemImage: note.symbolName)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(note == .crosses ? .orange : .green)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Same route

    @ViewBuilder
    private var sameRouteContent: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Label("Fastest is already the safest", systemImage: "checkmark.shield.fill")
                .font(.title3.weight(.bold))
                .foregroundStyle(.green)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if isReloading {
                ProgressView()
                    .controlSize(.small)
            }
            if result.isLiveTraffic {
                liveTrafficPill
            }
        }

        closureLine

        HStack(spacing: 10) {
            Circle()
                .fill(.green)
                .frame(width: 10, height: 10)
            Text("\(displayedMinutes(safest)) min")
                .font(.title2.weight(.bold))
                .monospacedDigit()
            Text(miles(safest))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }

        VStack(alignment: .leading, spacing: 6) {
            Text("Heads up on this route")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
            let hazards = safest.maneuverHazardCounts
            if hazards.isEmpty {
                Text("No risky merges or busy left turns on this route.")
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                chipGrid(hazards, tint: .orange)
            }
        }
    }

    // MARK: - Details

    private var details: some View {
        DisclosureGroup(isExpanded: $showsDetails) {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                GridRow {
                    Text(response.routesAreIdentical ? "Distance" : "Safe route")
                    Text(miles(safest))
                }
                if !response.routesAreIdentical {
                    GridRow {
                        Text("Fastest route")
                        Text(miles(fastest))
                    }
                    GridRow {
                        Text("Risk reduction")
                        Text("\(Int(response.comparison.riskReductionPct.rounded()))%")
                    }
                }
                if result.isDemoData {
                    GridRow {
                        Text("Source")
                        Text("Demo data")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .foregroundStyle(.orange)
                            .background(.orange.opacity(0.18), in: Capsule())
                    }
                }
            }
            .font(.footnote)
            .foregroundStyle(.secondary)
            .padding(.top, 6)
        } label: {
            Text("Details")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
        }
        .tint(.secondary)
    }

    // MARK: - Helpers

    /// Whole minutes as displayed, so the badge always agrees with the two ETAs.
    private func displayedMinutes(_ route: Route) -> Int {
        Int(route.etaMinutes.rounded())
    }

    private func miles(_ route: Route) -> String {
        String(format: "%.1f mi", route.distanceMiles)
    }

    /// 1...5 dots, relative to the riskier of the two routes (which always shows 5).
    private func riskDots(for route: Route) -> Int {
        let top = max(fastest.riskScore, safest.riskScore)
        guard top > 0 else { return 1 }
        return min(5, max(1, Int((route.riskScore / top * 5).rounded())))
    }

    private func riskLabel(for route: Route) -> String {
        if fastest.riskScore == safest.riskScore { return "Same risk" }
        let isSafer = route.riskScore == min(fastest.riskScore, safest.riskScore)
        return isSafer ? "Lower risk" : "Higher risk"
    }
}

/// Five dots, `filled` of them solid.
private struct RiskMeter: View {
    let filled: Int
    let color: Color

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<5, id: \.self) { index in
                Circle()
                    .fill(index < filled ? color : color.opacity(0.25))
                    .frame(width: 7, height: 7)
            }
        }
        .accessibilityLabel("Risk \(filled) of 5")
    }
}
