//
//  OnboardingFlow.swift
//  SafeRoute
//

import CoreLocation
import SwiftUI

/// First-launch onboarding, shown after the boot screen: pick who is driving (saved as the profile),
/// then decide about location. Shown once (`Config.onboardingStorageKey`), or again from the profile
/// button's long press for demos. Large type throughout because elderly drivers are a target user.
struct OnboardingFlow: View {
    let locationManager: LocationManager
    /// `declinedLocation` is true after "Not now", so the map does not show the system prompt right away.
    var onFinish: (_ declinedLocation: Bool) -> Void

    @AppStorage(Config.profileStorageKey) private var storedProfile: Profile = .teen
    @State private var step: Step = .profile

    private enum Step {
        case profile, location
    }

    var body: some View {
        ZStack {
            OnboardingBackground()
            switch step {
            case .profile:
                ProfileStep { profile in
                    storedProfile = profile
                    withAnimation(.spring(duration: 0.5, bounce: 0.15)) {
                        step = .location
                    }
                }
                .transition(Self.stepTransition)
            case .location:
                LocationStep(
                    onAllow: {
                        locationManager.requestPermission()
                        // Already answered on an earlier launch (a demo replay): nothing to wait for.
                        if locationManager.hasDecidedPermission {
                            onFinish(false)
                        }
                    },
                    onSkip: { onFinish(true) }
                )
                .transition(Self.stepTransition)
            }
        }
        .environment(\.colorScheme, .light)  // the brand background is light; keep text and glass for it
        .onChange(of: locationManager.authorizationStatus) { _, _ in
            // The system prompt was answered, either way: on to the map.
            if step == .location, locationManager.hasDecidedPermission {
                onFinish(false)
            }
        }
        .sensoryFeedback(.selection, trigger: step)
    }

    /// New screen slides in from the right while the old one leaves to the left.
    private static let stepTransition: AnyTransition = .asymmetric(
        insertion: .move(edge: .trailing).combined(with: .opacity),
        removal: .move(edge: .leading).combined(with: .opacity)
    )
}

// MARK: - Screen 1: who's driving

private struct ProfileStep: View {
    var onPick: (Profile) -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 16)
            Image(.safeRouteLogo)
                .resizable()
                .scaledToFit()
                .frame(height: 68)
                .accessibilityHidden(true)
            Text("Who's driving?")
                .font(.system(.title, design: .rounded, weight: .bold))
                .foregroundStyle(Brand.navy)
                .padding(.top, 14)
            Text("Pick who's in the car. You can change this any time from the map.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.top, 6)
                .padding(.horizontal, 8)
            Spacer(minLength: 24)
            GlassEffectContainer(spacing: 12) {
                VStack(spacing: 12) {
                    ForEach(Profile.allCases) { profile in
                        ProfileCard(profile: profile) {
                            onPick(profile)
                        }
                    }
                }
            }
            Spacer(minLength: 24)
        }
        // A column narrower than the screen, so the cards sit in the space instead of spanning it.
        .frame(maxWidth: 340)
        .padding(.horizontal, 28)
    }
}

/// One large glass card: symbol in a colored circle, the title and one line on what SafeRoute watches for.
private struct ProfileCard: View {
    let profile: Profile
    var onTap: () -> Void

    private let shape = RoundedRectangle(cornerRadius: 22, style: .continuous)

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                Image(systemName: profile.symbolName)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 48, height: 48)
                    .background(profile.accent, in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(profile.onboardingTitle)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    Text(profile.onboardingLine)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassEffect(.regular.interactive(), in: shape)
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
    }
}

private extension Profile {
    /// Logo color behind each profile's symbol.
    var accent: Color {
        switch self {
        case .teen: Brand.skyBlue
        case .elderly: Brand.navy
        case .sensitivePassenger: Brand.coral
        }
    }
}

// MARK: - Screen 2: location

private struct LocationStep: View {
    var onAllow: () -> Void
    var onSkip: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "location.fill")
                .font(.system(size: 36, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 84, height: 84)
                .background(Brand.skyBlue, in: Circle())
                .accessibilityHidden(true)
            Text("Start from where you are")
                .font(.system(.title, design: .rounded, weight: .bold))
                .foregroundStyle(Brand.navy)
                .multilineTextAlignment(.center)
                .padding(.top, 22)
            Text("SafeRoute uses your location to plan the safest route from where you are.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.top, 10)
                .padding(.horizontal, 8)
            Spacer()
            Button(action: onAllow) {
                Label("Allow location", systemImage: "location.fill")
                    .font(.headline)
            }
            .buttonStyle(SolidButtonStyle(fill: Brand.navy))
            .accessibilityHint("Shows the system location permission prompt.")
            Button("Not now", action: onSkip)
                .buttonStyle(.plain)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 18)
                .padding(.bottom, 8)
        }
        .frame(maxWidth: 340)
        .padding(.horizontal, 28)
        .padding(.bottom, 16)
    }
}

// MARK: - Shared pieces

/// The brand cream with a soft wash of the logo's sky blue and sunset coral for the glass cards to pick up.
private struct OnboardingBackground: View {
    var body: some View {
        ZStack {
            Brand.background
            Circle()
                .fill(Brand.skyBlue.opacity(0.45))
                .frame(width: 440, height: 440)
                .blur(radius: 90)
                .offset(x: -140, y: -320)
            Circle()
                .fill(Brand.coral.opacity(0.45))
                .frame(width: 400, height: 400)
                .blur(radius: 90)
                .offset(x: 150, y: 300)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

/// Full-width solid block with white content, dimming while pressed (the Start button's look).
private struct SolidButtonStyle: ButtonStyle {
    let fill: Color

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
        return configuration.label
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: shape)
            .contentShape(shape)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

#Preview {
    OnboardingFlow(locationManager: LocationManager()) { _ in }
}
