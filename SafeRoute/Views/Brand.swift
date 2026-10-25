//
//  Brand.swift
//  SafeRoute
//

import SwiftUI

/// Colors sampled from the logo (SafeRouteLogo.png) for the app icon, the boot screen and onboarding.
/// Main-actor like the views that use it: the generated `ColorResource` symbols are main-actor isolated.
enum Brand {
    /// The pale cream at the sun's rim (#F9DEBF): the app icon background, the boot screen and the
    /// onboarding background. Lives in the asset catalog as `BootBackground` so the launch screen can use it too.
    static let background = Color(.bootBackground)
    /// The deep teal-navy of the hills (#113D52): headline text and primary buttons.
    static let navy = Color(red: 0.067, green: 0.239, blue: 0.322)
    /// The sky at the top of the shield (#4994D5).
    static let skyBlue = Color(red: 0.286, green: 0.580, blue: 0.835)
    /// The sunset band (#FD9779).
    static let coral = Color(red: 0.992, green: 0.592, blue: 0.475)
}
