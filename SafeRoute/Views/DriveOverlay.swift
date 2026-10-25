//
//  DriveOverlay.swift
//  SafeRoute
//

import SwiftUI

/// Top banner while driving: the next hazard ahead, or the drive's status. Large type throughout,
/// since elderly drivers are a target user.
struct DriveBanner: View {
    let banner: DriveModel.Banner
    let isMuted: Bool
    var onToggleMute: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: symbolName)
                .font(.title.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 56, height: 56)
                .background(tint, in: Circle())
                .contentTransition(.symbolEffect(.replace))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.title.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
                if let subtitle {
                    Text(subtitle)
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)

            Spacer(minLength: 8)

            Button(action: onToggleMute) {
                Image(systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                    .font(.title2.weight(.semibold))
                    .frame(width: 48, height: 48)
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(isMuted ? "Unmute spoken alerts" : "Mute spoken alerts")
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .animation(.snappy(duration: 0.25), value: banner)
    }

    private var title: String {
        switch banner {
        case .hazard(let event, let meters): "\(DriveFormat.hazardTitle(event)) in \(DriveFormat.distance(meters: meters))"
        case .clear: "No hazards ahead"
        case .offRoute: "Off route"
        case .arrived: "You've arrived"
        }
    }

    private var subtitle: String? {
        switch banner {
        case .hazard(let event, _): event.description
        case .clear: "Follow the green route"
        case .offRoute: "Finding a new route…"
        case .arrived: nil
        }
    }

    private var symbolName: String {
        switch banner {
        case .hazard(let event, _): event.kind.symbolName
        case .clear: "shield.checkered"
        case .offRoute: "location.slash.fill"
        case .arrived: "flag.checkered"
        }
    }

    private var tint: Color {
        switch banner {
        case .hazard(let event, _):
            switch event.kind {
            case .leftTurn, .quickExitTurn: .orange
            case .leftTurnMajor, .highwayMerge, .highCrashZone: .red
            case .unknown: .gray
            }
        case .clear, .arrived: .green
        case .offRoute: .orange
        }
    }
}

/// Bottom bar while driving: time and distance left, arrival time, and the End button.
struct DriveBottomBar: View {
    let stats: DriveStats?
    var isSimulated = false
    var onEnd: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            if isSimulated {
                Text("Simulated")
                    .font(.caption.weight(.bold))
                    .textCase(.uppercase)
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(.orange.opacity(0.18), in: Capsule())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityLabel("Simulated drive")
            }
            if let stats {
                HStack(alignment: .firstTextBaseline) {
                    stat(DriveFormat.duration(minutes: stats.remainingMinutes), label: "left")
                    Spacer()
                    stat(DriveFormat.distance(meters: stats.remainingMeters), label: "to go")
                    Spacer()
                    stat(DriveFormat.clockTime(stats.arrival), label: "arrival")
                }
            }

            Button(action: onEnd) {
                Text("End")
                    .font(.title2.weight(.bold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(.capsule)
            .controlSize(.large)
            .tint(.red)
            .accessibilityHint("Ends drive mode")
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private func stat(_ value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(value)
                .font(.title2.weight(.bold))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    VStack {
        DriveBanner(
            banner: .hazard(RiskEvent(type: "left_turn_major", lat: 0, lng: 0, description: "Left turn across Lamar Blvd"), metersAhead: 480),
            isMuted: false,
            onToggleMute: {}
        )
        Spacer()
        DriveBottomBar(stats: DriveStats(remainingMinutes: 12, remainingMeters: 3800, arrival: .now), isSimulated: true, onEnd: {})
    }
    .padding()
}
