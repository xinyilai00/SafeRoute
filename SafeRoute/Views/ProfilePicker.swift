//
//  ProfilePicker.swift
//  SafeRoute
//

import SwiftUI

/// Circular glass button showing the current profile's symbol; opens a menu of the three profiles.
struct ProfilePicker: View {
    @Binding var selection: Profile

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
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .accessibilityLabel("Profile: \(selection.displayName)")
    }
}

#Preview {
    @Previewable @State var profile: Profile = .teen
    ProfilePicker(selection: $profile).padding()
}
