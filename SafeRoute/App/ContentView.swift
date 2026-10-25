//
//  ContentView.swift
//  SafeRoute
//
//  Created by Sihan Zhang on 10/24/26.
//

import SwiftUI

/// Root of the app. A cold launch shows `BootScreen` over everything for about a second; underneath it
/// the first launch gets `OnboardingFlow` and every later launch the map. The risk grid fetch starts
/// right away so nothing waits on it. The location manager and screen model live here because
/// onboarding asks for location permission and the map uses the result.
struct ContentView: View {
    @AppStorage(Config.onboardingStorageKey) private var hasCompletedOnboarding = false
    /// Mirrors the flag as view state so the switch between onboarding and the map animates.
    @State private var showsOnboarding: Bool
    @State private var isBooting = true
    @State private var model = MapScreenModel()
    @State private var locationManager = LocationManager()
    /// False after onboarding's "Not now", so the map does not show the system prompt right away.
    @State private var promptsForLocation = true

    init() {
        _showsOnboarding = State(initialValue: !UserDefaults.standard.bool(forKey: Config.onboardingStorageKey))
    }

    var body: some View {
        ZStack {
            if showsOnboarding {
                OnboardingFlow(locationManager: locationManager, onFinish: finishOnboarding)
                    .transition(.opacity)
            } else {
                MapScreen(
                    locationManager: locationManager,
                    model: model,
                    promptsForLocationOnAppear: promptsForLocation,
                    onResetOnboarding: showOnboardingAgain
                )
                .transition(.opacity)
            }
            if isBooting {
                BootScreen {
                    isBooting = false
                }
                .zIndex(1)
            }
        }
        .task {
            model.loadRiskGridIfNeeded()
        }
    }

    private func finishOnboarding(declinedLocation: Bool) {
        promptsForLocation = !declinedLocation
        hasCompletedOnboarding = true
        withAnimation(.easeInOut(duration: 0.45)) {
            showsOnboarding = false
        }
    }

    /// Demo hook from the profile button: back to the welcome screens, with the map reset to neutral.
    private func showOnboardingAgain() {
        model.clearDestination()
        promptsForLocation = true
        hasCompletedOnboarding = false
        withAnimation(.easeInOut(duration: 0.45)) {
            showsOnboarding = true
        }
    }
}

#Preview {
    ContentView()
}
