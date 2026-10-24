//
//  ProfilePicker.swift
//  SafeRoute
//

import SwiftUI

/// Segmented control for the three rider profiles.
struct ProfilePicker: View {
    @Binding var selection: Profile

    var body: some View {
        Picker("Profile", selection: $selection) {
            ForEach(Profile.allCases) { profile in
                Text(profile.shortName).tag(profile)
            }
        }
        .pickerStyle(.segmented)
    }
}

#Preview {
    @Previewable @State var profile: Profile = .teen
    ProfilePicker(selection: $profile).padding()
}
