//
//  HazardMarkers.swift
//  SafeRoute
//

import SwiftUI

/// Circular map marker for one hazard cluster, colored by its most serious hazard, with a count badge
/// when several hazards were merged. Tapping toggles a bubble listing every hazard in it.
struct HazardClusterMarker: View {
    let cluster: HazardCluster
    var isSelected: Bool
    var onTap: () -> Void

    private var isMerged: Bool { cluster.count > 1 }
    private var size: CGFloat { isMerged ? 26 : 22 }

    var body: some View {
        Button(action: onTap) {
            Image(systemName: cluster.primaryKind.symbolName)
                .font(.system(size: isMerged ? 12 : 11, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(color, in: Circle())
                .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
                .overlay(alignment: .topTrailing) {
                    if isMerged {
                        countBadge
                    }
                }
                .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
        }
        .buttonStyle(.plain)
        .overlay(alignment: .bottom) {
            if isSelected {
                bubble
            }
        }
        .animation(.snappy(duration: 0.2), value: isSelected)
        .accessibilityLabel(accessibilityText)
        .accessibilityHint("Shows what is here")
    }

    private var countBadge: some View {
        Text("\(cluster.count)")
            .font(.system(size: 10, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(color)
            .frame(minWidth: 16, minHeight: 16)
            .background(.white, in: Capsule())
            .shadow(color: .black.opacity(0.2), radius: 1, y: 0.5)
            .offset(x: 7, y: -7)
    }

    /// The hazards here, one line each, floating above the marker.
    private var bubble: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(cluster.events) { event in
                Label(event.description, systemImage: event.kind.symbolName)
                    .font(.caption)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .frame(maxWidth: 260)
        .padding(.bottom, size + 8)
        .transition(.opacity.combined(with: .scale(scale: 0.9, anchor: .bottom)))
    }

    private var color: Color {
        switch cluster.primaryKind {
        case .leftTurn, .quickExitTurn: .orange
        case .leftTurnMajor, .highwayMerge, .highCrashZone: .red
        case .unknown: .gray
        }
    }

    private var accessibilityText: String {
        isMerged
            ? "\(cluster.count) hazards: " + cluster.events.map(\.description).joined(separator: "; ")
            : cluster.events.first?.description ?? "Hazard"
    }
}
