//
//  MapScreen.swift
//  SafeRoute
//

import MapKit
import SwiftUI

/// Full-screen map: user location, destination search, fastest/safest routes, and the summary card.
struct MapScreen: View {
    @State private var locationManager = LocationManager()
    @State private var model = MapScreenModel()
    @State private var cameraPosition: MapCameraPosition = .userLocation(fallback: .region(Config.austinRegion))
    @Namespace private var mapScope

    /// Height reserved at the top so camera fitting keeps routes out from under the search field.
    private let searchBarReserve: CGFloat = 64

    var body: some View {
        ZStack(alignment: .top) {
            Map(position: $cameraPosition, scope: mapScope) {
                UserAnnotation()

                if model.showHeatmap {
                    ForEach(model.heatmapCells) { cell in
                        MapPolygon(coordinates: cell.ring)
                            .foregroundStyle(HeatmapStyle.color(for: cell.risk).opacity(HeatmapStyle.opacity(for: cell.risk)))
                    }
                }

                if let result = model.result {
                    MapPolyline(coordinates: result.response.fastest.coordinates)
                        .stroke(.gray, style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
                    MapPolyline(coordinates: result.response.safest.coordinates)
                        .stroke(.green, style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
                    ForEach(result.response.safest.riskEvents) { event in
                        Annotation(event.description, coordinate: event.coordinate, anchor: .center) {
                            RiskEventMarker(kind: event.kind)
                        }
                        .annotationTitles(.hidden)
                    }
                }

                if let destination = model.destination {
                    Marker(
                        destination.name ?? "Destination",
                        systemImage: "mappin",
                        coordinate: destination.location.coordinate
                    )
                    .tint(.red)
                }
            }
            .safeAreaInset(edge: .top, spacing: 0) {
                Color.clear
                    .frame(height: searchBarReserve)
                    .allowsHitTesting(false)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                bottomPanel
            }

            if model.showHeatmap {
                HeatmapLegend(isDemoData: model.isHeatmapDemoData)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .padding(.leading, 16)
                    .padding(.top, searchBarReserve + 12)
                    .transition(.opacity)
                    .allowsHitTesting(false)
            }

            SearchBar(userLocation: locationManager.coordinate) { item in
                model.selectDestination(item)
                frameCamera(around: item.location.coordinate)
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
        }
        .mapScope(mapScope)
        .ignoresSafeArea(.keyboard)
        .onAppear { locationManager.start() }
        .onChange(of: model.profile) { _, _ in
            // Re-request only if a route is showing or being fetched; otherwise wait for the button.
            if model.result != nil || model.isLoading {
                findRoute()
            }
        }
        .onChange(of: model.result) { _, result in
            if let result {
                fitCamera(to: result)
            }
        }
    }

    // MARK: - Bottom panel

    private var bottomPanel: some View {
        VStack(alignment: .trailing, spacing: 12) {
            HStack(alignment: .bottom) {
                HeatmapToggle(isOn: $model.showHeatmap, isLoading: model.isHeatmapLoading)
                Spacer()
                MapUserLocationButton(scope: mapScope)
            }

            if model.destination != nil {
                ProfilePicker(selection: $model.profile)

                if model.result != nil {
                    SafetySlider(value: $model.safetyWeight) { findRoute() }
                }

                if let result = model.result {
                    RouteSummaryCard(result: result, isReloading: model.isLoading)
                } else {
                    findRouteButton
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }

    private var findRouteButton: some View {
        Button {
            findRoute()
        } label: {
            HStack(spacing: 8) {
                if model.isLoading {
                    ProgressView()
                } else {
                    Image(systemName: "shield.checkered")
                }
                Text(model.isLoading ? "Finding safest route…" : "Find safest route")
            }
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
        }
        .buttonStyle(.glass)
        .controlSize(.large)
        .disabled(model.isLoading)
    }

    // MARK: - Actions

    private func findRoute() {
        model.findRoute(from: locationManager.coordinate)
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

    /// Fits both routes in the visible map area (the safe-area insets keep them clear of the UI).
    private func fitCamera(to result: RouteResult) {
        let coordinates = result.response.fastest.coordinates + result.response.safest.coordinates
        guard !coordinates.isEmpty else { return }
        let rect = MKPolyline(coordinates: coordinates, count: coordinates.count).boundingMapRect
        let padded = rect.insetBy(dx: -rect.width * 0.2, dy: -rect.height * 0.2)
        withAnimation(.easeInOut(duration: 0.8)) {
            cameraPosition = .rect(padded)
        }
    }
}

/// Small circular marker for one hazard on the safest route.
private struct RiskEventMarker: View {
    let kind: RiskEventType

    var body: some View {
        Image(systemName: kind.symbolName)
            .font(.system(size: 11, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: 22, height: 22)
            .background(color, in: Circle())
            .overlay(Circle().strokeBorder(.white, lineWidth: 1.5))
            .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
    }

    private var color: Color {
        switch kind {
        case .leftTurn, .quickExitTurn: .orange
        case .leftTurnMajor, .highwayMerge, .highCrashZone: .red
        case .unknown: .gray
        }
    }
}

#Preview {
    MapScreen()
}
