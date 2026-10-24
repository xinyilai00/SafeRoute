//
//  MapScreen.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// Full-screen map with the user's location, a destination search bar, and the chosen destination pin.
struct MapScreen: View {
    @State private var locationManager = LocationManager()
    @State private var cameraPosition: MapCameraPosition = .userLocation(fallback: .region(Config.austinRegion))
    /// Destination picked from search. `destination.location.coordinate` is what routing uses.
    @State private var destination: MKMapItem?
    @Namespace private var mapScope

    var body: some View {
        ZStack(alignment: .top) {
            Map(position: $cameraPosition, scope: mapScope) {
                UserAnnotation()
                if let destination {
                    Marker(
                        destination.name ?? "Destination",
                        systemImage: "mappin",
                        coordinate: destination.location.coordinate
                    )
                    .tint(.red)
                }
            }
            .ignoresSafeArea()

            SearchBar(userLocation: locationManager.coordinate) { item in
                destination = item
                frameCamera(around: item.location.coordinate)
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
        }
        .overlay(alignment: .bottomTrailing) {
            MapUserLocationButton(scope: mapScope)
                .padding(20)
        }
        .mapScope(mapScope)
        .ignoresSafeArea(.keyboard)
        .onAppear { locationManager.start() }
    }

    /// Zooms to show the destination and, when known, the user's location.
    private func frameCamera(around target: CLLocationCoordinate2D) {
        var points = [target]
        if let user = locationManager.coordinate {
            points.append(user)
        }
        let lats = points.map(\.latitude)
        let lons = points.map(\.longitude)
        guard let minLat = lats.min(), let maxLat = lats.max(),
              let minLon = lons.min(), let maxLon = lons.max() else { return }

        let center = CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2, longitude: (minLon + maxLon) / 2)
        let span = MKCoordinateSpan(
            latitudeDelta: max((maxLat - minLat) * 1.6, 0.015),
            longitudeDelta: max((maxLon - minLon) * 1.6, 0.015)
        )
        withAnimation(.easeInOut(duration: 0.6)) {
            cameraPosition = .region(MKCoordinateRegion(center: center, span: span))
        }
    }
}

#Preview {
    MapScreen()
}
