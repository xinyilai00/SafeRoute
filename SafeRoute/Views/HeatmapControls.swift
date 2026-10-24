//
//  HeatmapControls.swift
//  SafeRoute
//

import SwiftUI

/// Color for a heatmap cell: pale yellow at low risk through orange to deep red.
nonisolated enum HeatmapStyle {
    static func color(for risk: Double) -> Color {
        let t = min(max((risk - 0.35) / 0.65, 0), 1)
        return Color(hue: 0.14 * (1 - t), saturation: 0.85, brightness: 0.95)
    }

    static func opacity(for risk: Double) -> Double { 0.18 + 0.32 * min(max(risk, 0), 1) }
}

/// Round toggle for the crash-risk overlay.
struct HeatmapToggle: View {
    @Binding var isOn: Bool
    var isLoading: Bool

    var body: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) { isOn.toggle() }
        } label: {
            ZStack {
                if isLoading {
                    ProgressView()
                } else {
                    Image(systemName: isOn ? "flame.fill" : "flame")
                        .foregroundStyle(isOn ? .red : .primary)
                }
            }
            .font(.system(size: 17, weight: .semibold))
            .frame(width: 44, height: 44)
            .background(.regularMaterial, in: Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isOn ? "Hide crash risk heatmap" : "Show crash risk heatmap")
    }
}

/// Small key shown while the heatmap is on.
struct HeatmapLegend: View {
    var isDemoData: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(isDemoData ? "Crash risk (sample area)" : "Crash risk")
                .font(.caption2.weight(.semibold))
            LinearGradient(
                colors: stride(from: 0.35, through: 1.0, by: 0.13).map { HeatmapStyle.color(for: $0) },
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: 120, height: 8)
            .clipShape(Capsule())
            HStack {
                Text("Lower").font(.caption2)
                Spacer()
                Text("Higher").font(.caption2)
            }
            .frame(width: 120)
            .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

/// Fastest <-> safest slider that drives `safety_weight`. The route is re-requested when the drag ends.
struct SafetySlider: View {
    @Binding var value: Double
    var onCommit: () -> Void

    var body: some View {
        VStack(spacing: 2) {
            Slider(value: $value, in: 0...1) { editing in
                if !editing { onCommit() }
            }
            HStack {
                Label("Fastest", systemImage: "hare.fill")
                Spacer()
                Label("Safest", systemImage: "shield.checkered")
            }
            .font(.caption2.weight(.medium))
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
    }
}
