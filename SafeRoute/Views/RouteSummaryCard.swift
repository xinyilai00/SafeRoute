//
//  RouteSummaryCard.swift
//  SafeRoute
//

import SwiftUI

/// Liquid Glass card comparing the safest route against the fastest one.
struct RouteSummaryCard: View {
    let result: RouteResult
    /// True while a new request (e.g. after a profile change) is replacing this result.
    var isReloading = false

    private var comparison: RouteComparison { result.response.comparison }
    private var safest: Route { result.response.safest }
    private var fastest: Route { result.response.fastest }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Label("Safest route", systemImage: "shield.checkered")
                    .font(.headline)
                Spacer()
                if isReloading {
                    ProgressView()
                        .controlSize(.small)
                }
                if result.isDemoData {
                    Text("Demo data")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .foregroundStyle(.orange)
                        .background(.orange.opacity(0.18), in: Capsule())
                }
            }

            Text(comparison.summary)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            HStack(spacing: 0) {
                stat(value: minutesAddedText, label: "Added time")
                Divider().frame(height: 32)
                stat(value: "\(Int(comparison.riskReductionPct.rounded()))%", label: "Less risk")
                Divider().frame(height: 32)
                stat(value: miles(safest.distanceMiles), label: "Distance")
            }

            HStack(spacing: 16) {
                routeLine(color: .green, name: "Safest", route: safest)
                routeLine(color: .gray, name: "Fastest", route: fastest)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private var minutesAddedText: String {
        let minutes = comparison.minutesAdded
        return minutes < 0.5 ? "+0 min" : String(format: "+%.0f min", minutes)
    }

    private func miles(_ value: Double) -> String {
        String(format: "%.1f mi", value)
    }

    private func stat(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.title3.weight(.semibold))
                .monospacedDigit()
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func routeLine(color: Color, name: String, route: Route) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text("\(name) · \(String(format: "%.0f", route.etaMinutes)) min · \(miles(route.distanceMiles))")
        }
    }
}
