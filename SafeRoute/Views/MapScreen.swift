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
    @FocusState private var isSearchFocused: Bool
    /// Marker whose description bubble is open: "fastest-<event id>" or "safest-<event id>".
    @State private var selectedEventKey: String?
    /// Where the "Safe · 24 min" / "Fastest · 23 min" capsules sit; recomputed when the result changes.
    @State private var labelAnchors: RouteLabelAnchors?
    /// Remembered between launches; mirrored into `model.profile`.
    @AppStorage(Config.profileStorageKey) private var storedProfile: Profile = .teen
    @AppStorage(Config.mapStyleStorageKey) private var mapStyleChoice: MapStyleChoice = .standard

    /// Height reserved at the top so camera fitting keeps routes out from under the search field.
    private let searchBarReserve: CGFloat = 64

    var body: some View {
        ZStack(alignment: .top) {
            Map(position: $cameraPosition) {
                UserAnnotation()

                if model.showsRiskHeatmap, let bands = model.riskBands {
                    RiskHeatmapLayer(bands: bands)
                }

                if let result = model.result {
                    // The gray route and its markers are what the safe route avoids; nothing to show when identical.
                    // White casings keep both lines legible on satellite and hybrid imagery.
                    if !result.response.routesAreIdentical {
                        MapPolyline(coordinates: result.response.fastest.coordinates)
                            .stroke(.white.opacity(0.85), style: StrokeStyle(lineWidth: 8, lineCap: .round, lineJoin: .round))
                        MapPolyline(coordinates: result.response.fastest.coordinates)
                            .stroke(.gray, style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
                    }
                    MapPolyline(coordinates: result.response.safest.coordinates)
                        .stroke(.white.opacity(0.85), style: StrokeStyle(lineWidth: 9, lineCap: .round, lineJoin: .round))
                    MapPolyline(coordinates: result.response.safest.coordinates)
                        .stroke(.green, style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))

                    if !result.response.routesAreIdentical {
                        ForEach(result.response.fastest.maneuverEvents) { event in
                            Annotation(event.description, coordinate: event.coordinate, anchor: .center) {
                                RiskEventMarker(
                                    event: event,
                                    isMuted: true,
                                    isSelected: selectedEventKey == "fastest-\(event.id)"
                                ) { toggleSelection("fastest-\(event.id)") }
                            }
                            .annotationTitles(.hidden)
                        }
                    }
                    ForEach(result.response.safest.maneuverEvents) { event in
                        Annotation(event.description, coordinate: event.coordinate, anchor: .center) {
                            RiskEventMarker(
                                event: event,
                                isMuted: false,
                                isSelected: selectedEventKey == "safest-\(event.id)"
                            ) { toggleSelection("safest-\(event.id)") }
                        }
                        .annotationTitles(.hidden)
                    }

                    if let labelAnchors {
                        Annotation("", coordinate: labelAnchors.safe, anchor: .bottom) {
                            RouteLabel(
                                text: result.response.routesAreIdentical
                                    ? "Fastest is already the safest"
                                    : "Safe · \(Int(result.response.safest.etaMinutes.rounded())) min",
                                color: .green
                            )
                        }
                        .annotationTitles(.hidden)
                        if let fast = labelAnchors.fast {
                            Annotation("", coordinate: fast, anchor: .bottom) {
                                RouteLabel(
                                    text: "Fastest · \(Int(result.response.fastest.etaMinutes.rounded())) min",
                                    color: Color(white: 0.42)
                                )
                            }
                            .annotationTitles(.hidden)
                        }
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
            .mapStyle(mapStyleChoice.mapStyle)
            // Runs alongside MapKit's own gestures: a tap anywhere on the map puts the keyboard away.
            .simultaneousGesture(TapGesture().onEnded { isSearchFocused = false })
            .safeAreaInset(edge: .top, spacing: 0) {
                Color.clear
                    .frame(height: searchBarReserve)
                    .allowsHitTesting(false)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                bottomPanel
            }

            // Top-right cluster under the search field; drawn before SearchBar so its dropdown covers it.
            GlassEffectContainer(spacing: 12) {
                VStack(spacing: 12) {
                    ProfilePicker(selection: $model.profile)
                    MapStyleMenu(selection: $mapStyleChoice)
                }
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding(.trailing, 16)
            .padding(.top, searchBarReserve + 8)

            SearchBar(
                userLocation: locationManager.coordinate,
                isFocused: $isSearchFocused,
                onSelect: { item in
                    model.selectDestination(item)
                    frameCamera(around: item.location.coordinate)
                    findRoute()
                },
                onClear: {
                    model.clearDestination()
                    recenterOnUser()
                }
            )
            .padding(.horizontal, 16)
            .padding(.top, 8)
        }
        .ignoresSafeArea(.keyboard)
        .onAppear {
            model.profile = storedProfile
            locationManager.start()
            model.loadRiskGridIfNeeded()
        }
        .onChange(of: model.profile) { _, profile in
            storedProfile = profile
            // Re-request with the new profile if a route is showing or being fetched.
            if model.result != nil || model.isLoading {
                findRoute()
            }
        }
        .onChange(of: model.result) { _, result in
            selectedEventKey = nil
            labelAnchors = result.map { RouteLabelPlacement.anchors(for: $0.response) } ?? nil
            if let result {
                fitCamera(to: result)
            }
        }
    }

    // MARK: - Bottom panel

    private var bottomPanel: some View {
        VStack(alignment: .trailing, spacing: 12) {
            // One glass cluster: the controls merge visually when they sit this close.
            GlassEffectContainer(spacing: 12) {
                HStack(spacing: 12) {
                    if model.isRiskGridAvailable {
                        heatmapToggle
                    }
                    recenterButton
                }
            }

            if model.destination != nil {
                if let result = model.result {
                    RouteSummaryCard(result: result, isReloading: model.isLoading)
                } else if model.isLoading {
                    loadingCard
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }

    private var recenterButton: some View {
        Button {
            recenterOnUser()
        } label: {
            Image(systemName: "location.fill")
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .glassEffect(.regular.interactive(), in: .circle)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Recenter on my location")
    }

    /// Shown in place of the summary card while the first route for a destination is loading.
    private var loadingCard: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text("Finding safest route…")
                .font(.headline)
            Spacer()
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private var heatmapToggle: some View {
        Button {
            model.showsRiskHeatmap.toggle()
        } label: {
            HStack(spacing: 6) {
                if model.riskBands == nil {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Image(systemName: model.showsRiskHeatmap ? "flame.fill" : "flame")
                        .foregroundStyle(model.showsRiskHeatmap ? .red : .primary)
                }
                Text("Risk map")
            }
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 16)
            .frame(height: 44)
            .glassEffect(.regular.interactive(), in: .capsule)
        }
        .buttonStyle(.plain)
        .disabled(model.riskBands == nil)
        .accessibilityLabel(model.showsRiskHeatmap ? "Hide risk map" : "Show risk map")
    }

    // MARK: - Actions

    private func findRoute() {
        model.findRoute(from: locationManager.coordinate)
    }

    private func toggleSelection(_ key: String) {
        selectedEventKey = selectedEventKey == key ? nil : key
    }

    /// Animates back to the user. `.userLocation` only moves on a new fix, so a stationary phone
    /// would not budge; centering on the last known coordinate always animates.
    private func recenterOnUser() {
        withAnimation(.easeInOut(duration: 0.6)) {
            if let user = locationManager.coordinate {
                cameraPosition = .region(MKCoordinateRegion(center: user, latitudinalMeters: 1_500, longitudinalMeters: 1_500))
            } else {
                cameraPosition = .userLocation(fallback: .region(Config.austinRegion))
            }
        }
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

/// Small circular marker for one maneuver hazard. Muted (small, gray) for the fastest route,
/// colored for the safest. Tapping toggles a bubble with the event's description.
private struct RiskEventMarker: View {
    let event: RiskEvent
    var isMuted: Bool
    var isSelected: Bool
    var onTap: () -> Void

    private var size: CGFloat { isMuted ? 16 : 22 }

    var body: some View {
        Button(action: onTap) {
            Image(systemName: event.kind.symbolName)
                .font(.system(size: isMuted ? 8 : 11, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(color, in: Circle())
                .overlay(Circle().strokeBorder(.white, lineWidth: isMuted ? 1 : 1.5))
                .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
        }
        .buttonStyle(.plain)
        .overlay(alignment: .bottom) {
            if isSelected {
                Text(event.description)
                    .font(.caption)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .frame(width: 240)
                    .padding(.bottom, size + 6)
                    .transition(.opacity.combined(with: .scale(scale: 0.9, anchor: .bottom)))
            }
        }
        .animation(.snappy(duration: 0.2), value: isSelected)
        .accessibilityLabel(event.description)
    }

    private var color: Color {
        if isMuted { return .gray }
        switch event.kind {
        case .leftTurn, .quickExitTurn: return .orange
        case .leftTurnMajor, .highwayMerge, .highCrashZone: return .red
        case .unknown: return .gray
        }
    }
}

#Preview {
    MapScreen()
}
