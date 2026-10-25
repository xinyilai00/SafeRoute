//
//  Profile.swift
//  SafeRoute
//

import Foundation

/// Driver / passenger profile. The raw value is the exact string the backend expects in `"profile"`.
nonisolated enum Profile: String, CaseIterable, Identifiable, Codable {
    case teen
    case elderly
    case sensitivePassenger = "sensitive_passenger"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .teen: "Teen"
        case .elderly: "Elderly"
        case .sensitivePassenger: "Sensitive Passenger"
        }
    }

    /// One line shown under the name in the profile menu.
    var summary: String {
        switch self {
        case .teen: "New driver. Avoids merges and fast left turns."
        case .elderly: "Fewer left turns and complex junctions."
        case .sensitivePassenger: "Smooth ride. Avoids sharp turns and rough roads."
        }
    }

    /// Short label (kept for compact layouts).
    var shortName: String {
        switch self {
        case .teen: "Teen"
        case .elderly: "Elderly"
        case .sensitivePassenger: "Sensitive"
        }
    }

    /// Card title on the onboarding screen.
    var onboardingTitle: String {
        switch self {
        case .teen: "Teen driver"
        case .elderly: "Elderly driver"
        case .sensitivePassenger: "Sensitive passenger"
        }
    }

    /// One line on the onboarding card: what SafeRoute watches out for with this profile.
    var onboardingLine: String {
        switch self {
        case .teen: "Watches for highway merges and fast left turns."
        case .elderly: "Watches for left turns across traffic and busy junctions."
        case .sensitivePassenger: "Watches for sharp curves and rough roads."
        }
    }

    /// SF Symbol shown next to the profile.
    var symbolName: String {
        switch self {
        case .teen: "graduationcap.fill"
        case .elderly: "eyeglasses"
        case .sensitivePassenger: "heart.fill"
        }
    }
}
