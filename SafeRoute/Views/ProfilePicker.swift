//
//  ProfilePicker.swift
//  SafeRoute
//

import SwiftUI

/// Circular glass button showing the current profile's symbol; opens a menu of the three profiles.
/// A one-second hold calls `onLongPress` (the demo hook that shows onboarding again).
struct ProfilePicker: View {
    @Binding var selection: Profile
    var onLongPress: (() -> Void)?

    var body: some View {
        Menu {
            Picker("Profile", selection: $selection) {
                ForEach(Profile.allCases) { profile in
                    Label {
                        Text(profile.displayName)
                        Text(profile.summary)
                    } icon: {
                        Image(systemName: profile.symbolName)
                    }
                    .tag(profile)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: selection.symbolName)
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .contentTransition(.symbolEffect(.replace))
                .glassEffect(.regular.interactive(), in: .circle)
                .brandGlow(in: .circle)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        // Runs alongside the menu's own touch handling so the hold is recognized even though the menu opens.
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 1.0).onEnded { _ in
                onLongPress?()
            }
        )
        .accessibilityLabel("Profile: \(selection.displayName)")
        .accessibilityHint(onLongPress == nil ? "" : "Hold to show the welcome screens again.")
    }
}

#Preview {
    @Previewable @State var profile: Profile = .teen
    ProfilePicker(selection: $profile).padding()
}
