//
//  MapScreen.swift
//  SafeRoute
//

import MapKit
import SwiftUI
import UIKit

/// Full-screen map: user location, destination search, fastest/safest routes, and the summary card.
struct MapScreen: View {
    /// Created by `ContentView` and shared with onboarding, which asks for location permission.
    let locationManager: LocationManager
    @Bindable var model: MapScreenModel
    /// False right after onboarding's "Not now", so the system prompt is not shown again until the next launch.
    var promptsForLocationOnAppear = true
    /// Demo hook: holding the profile button shows onboarding again.
    var onResetOnboarding: () -> Void = {}
    @State private var cameraPosition: MapCameraPosition = .userLocation(fallback: .region(Config.austinRegion))
    @FocusState private var isSearchFocused: Bool
    /// Hazard markers in the route overview; recomputed when the result changes.
    @State private var hazardClusters: [HazardCluster] = []
    /// Marker whose bubble is open.
    @State private var selectedClusterID: HazardCluster.ID?
    /// Where the "Safe · 24 min" / "Fastest · 23 min" capsules sit; recomputed when the result changes.
    @State private var labelAnchors: RouteLabelAnchors?
    /// Remembered between launches; mirrored into `model.profile`.
    @AppStorage(Config.profileStorageKey) private var storedProfile: Profile = .teen
    @AppStorage(Config.mapStyleStorageKey) private var mapStyleChoice: MapStyleChoice = .standard
    /// Route options: road types to steer clear of. Off by default because they often save real time.
    @AppStorage(Config.avoidTollsStorageKey) private var avoidTolls = false
    @AppStorage(Config.avoidHighwaysStorageKey) private var avoidHighways = false
    /// Links the stand-alone `MapCompass` in the button column to this map.
    @Namespace private var mapScope
    /// Non-nil while drive mode is on.
    @State private var drive: DriveModel?
    /// Car arrow and the map heading it is drawn against; both move inside the camera animation so the arrow glides with the map.
    @State private var car: DriveCar?
    @State private var cameraHeading: Double = 0

    private var isDriving: Bool { drive != nil }

    /// True while the bottom panel shows a card (route, loading or coverage); the bottom glow follows it.
    private var showsRouteCard: Bool {
        !isDriving && model.destination != nil && (model.result != nil || model.isOutsideCoverage || model.isLoading)
    }

    /// Height reserved at the top so camera fitting keeps routes out from under the search field,
    /// which grows into the two-line From / To panel once a destination is chosen.
    private var searchBarReserve: CGFloat { model.destination == nil ? 64 : 104 }

    var body: some View {
        ZStack(alignment: .top) {
            Map(position: $cameraPosition, scope: mapScope) {
                // A simulated drive has its own car; the real blue dot would sit somewhere else entirely.
                if drive?.isSimulated != true {
                    UserAnnotation()
                }

                if model.showsRiskHeatmap, let bands = model.riskBands {
                    RiskHeatmapLayer(bands: bands, opacity: isDriving ? 0.35 : 1)
                }

                if let result = model.result {
                    // The gray route and its markers are what the safe route avoids; nothing to show when identical,
                    // and drive mode shows only the route being driven.
                    // White casings keep both lines legible on satellite and hybrid imagery.
                    if !result.response.routesAreIdentical && !isDriving {
                        MapPolyline(coordinates: result.response.fastest.coordinates)
                            .stroke(.white.opacity(0.85), style: StrokeStyle(lineWidth: 8, lineCap: .round, lineJoin: .round))
                        MapPolyline(coordinates: result.response.fastest.coordinates)
                            .stroke(.gray, style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
                    }
                    MapPolyline(coordinates: result.response.safest.coordinates)
                        .stroke(.white.opacity(0.85), style: StrokeStyle(lineWidth: 9, lineCap: .round, lineJoin: .round))
                    MapPolyline(coordinates: result.response.safest.coordinates)
                        .stroke(.green, style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))

                    // Overview markers: the hazards the safe route avoids (or, for identical routes, the route's
                    // own), merged when they would overlap. The safe line stays clean; drive mode calls out its hazards.
                    if !isDriving {
                        ForEach(hazardClusters) { cluster in
                            Annotation("", coordinate: cluster.coordinate, anchor: .center) {
                                HazardClusterMarker(cluster: cluster, isSelected: selectedClusterID == cluster.id) {
                                    toggleSelection(cluster.id)
                                }
                            }
                            .annotationTitles(.hidden)
                        }
                    }

                    if let labelAnchors, !isDriving {
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

                if let origin = model.origin {
                    Marker(origin.name ?? "Start", systemImage: "flag.fill", coordinate: origin.location.coordinate)
                        .tint(.green)
                }
                if let destination = model.destination {
                    Marker(
                        destination.name ?? "Destination",
                        systemImage: "mappin",
                        coordinate: destination.location.coordinate
                    )
                    .tint(.red)
                }

                if let car {
                    Annotation("", coordinate: car.coordinate, anchor: .center) {
                        DriveCarMarker(rotation: car.bearing - cameraHeading)
                    }
                    .annotationTitles(.hidden)
                }
            }
            .mapStyle(mapStyleChoice.mapStyle)
            // Default controls are a compass (when rotated) and a scale (while zooming). The compass would
            // overlap the profile button, so only the scale stays here; the compass lives in the button column.
            .mapControls {
                MapScaleView()
            }
            // Runs alongside MapKit's own gestures: a tap anywhere on the map puts the keyboard away.
            .simultaneousGesture(TapGesture().onEnded { isSearchFocused = false })
            // Atmosphere, added before the insets so the card and the drive banner draw above it. `ScreenEdges`
            // stretches each layer to the physical top and bottom of the screen; an overlay on the Map otherwise
            // stops at the device's own safe-area insets.
            .overlay {
                ScreenEdges {
                    VStack(spacing: 0) {
                        TopEdgeBlur()
                        Spacer(minLength: 0)
                    }
                }
            }
            .overlay {
                ScreenEdges {
                    VStack(spacing: 0) {
                        Spacer(minLength: 0)
                        if showsRouteCard {
                            BottomGlow()
                                .transition(.opacity)
                        }
                    }
                    .animation(.easeInOut(duration: 0.5), value: showsRouteCard)
                }
            }
            .safeAreaInset(edge: .top, spacing: 0) {
                if let drive {
                    DriveBanner(banner: drive.banner, isMuted: drive.isMuted, onToggleMute: drive.toggleMute)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                } else {
                    Color.clear
                        .frame(height: searchBarReserve)
                        .allowsHitTesting(false)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if let drive {
                    DriveBottomBar(stats: drive.stats, isSimulated: drive.isSimulated, onEnd: endDrive)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                } else {
                    bottomPanel
                }
            }

            if !isDriving {
                browsingOverlays
            }
        }
        .mapScope(mapScope)
        .ignoresSafeArea(.keyboard)
        .onAppear {
            model.profile = storedProfile
            locationManager.start(requestingPermission: promptsForLocationOnAppear)
            model.loadRiskGridIfNeeded()
        }
        .onChange(of: model.profile) { _, profile in
            storedProfile = profile
            refetchIfRouting()
        }
        .onChange(of: avoidTolls) { _, _ in refetchIfRouting() }
        .onChange(of: avoidHighways) { _, _ in refetchIfRouting() }
        .onChange(of: model.result) { _, result in
            selectedClusterID = nil
            labelAnchors = result.map { RouteLabelPlacement.anchors(for: $0.response) } ?? nil
            hazardClusters = result.map { HazardClustering.overviewClusters(for: $0.response) } ?? []
            if let result {
                if let drive {
                    drive.replaceRoute(result.response.safest)  // reroute while driving
                } else {
                    fitCamera(to: result)
                }
            }
        }
        .onChange(of: locationManager.location) { _, location in
            if let drive, !drive.isSimulated, let location {
                drive.update(with: location)
            }
        }
        .onChange(of: drive?.camera) { _, camera in
            if let camera {
                follow(camera)
            }
        }
        .onChange(of: drive?.rerouteRequests) { old, new in
            if let new, new > (old ?? 0) {
                findRoute()  // from the current location
            }
        }
        .onChange(of: drive?.isFinished) { _, finished in
            if finished == true {
                endDrive()
            }
        }
        // A light tap with every alert, spoken or muted.
        .sensoryFeedback(.impact(weight: .light), trigger: drive?.alertCount) { old, new in
            (new ?? 0) > (old ?? 0)
        }
    }

    /// Search field and the button column: everything that is not needed while driving.
    @ViewBuilder
    private var browsingOverlays: some View {
        // Top-right cluster under the search field; drawn before SearchBar so its dropdown covers it.
        GlassEffectContainer(spacing: 12) {
            VStack(spacing: 12) {
                ProfilePicker(selection: $model.profile, onLongPress: onResetOnboarding)
                MapStyleMenu(selection: $mapStyleChoice)
                RouteOptionsMenu(avoidTolls: $avoidTolls, avoidHighways: $avoidHighways)
                // Shows itself only while the map is not facing north, like the system compass.
                MapCompass(scope: mapScope)
                    .mapControlVisibility(.automatic)
                    .frame(width: 44, height: 44)
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.trailing, 16)
        .padding(.top, searchBarReserve + 8)

        SearchBar(
            userLocation: locationManager.coordinate,
            endpoints: model.destination.map { destination in
                SearchBar.Endpoints(
                    originName: model.origin?.name,
                    destinationName: destination.name ?? "Destination",
                    canSwap: model.origin != nil || locationManager.location != nil
                )
            },
            isFocused: $isSearchFocused,
            onSelect: { field, item in
                switch field {
                case .destination:
                    guard let item else { return }
                    model.selectDestination(item)
                    frameCamera(around: item.location.coordinate)
                case .origin:
                    model.selectOrigin(item)
                }
                findRoute()
            },
            onSwap: {
                model.swapEndpoints(userLocation: locationManager.location)
                findRoute()
            },
            onClear: clearRoute
        )
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }

    // MARK: - Bottom panel

    /// Space left between the card and the controls floating above it, where MapKit draws its attribution.
    private let attributionGap: CGFloat = 28

    /// With a route up, the card is the only thing that insets the map, so MapKit's "Apple Maps" / "Legal"
    /// attribution sits right above the card as in Apple Maps. The Risk map and recenter controls float above
    /// the card as an overlay, outside the inset; without a route they are the inset themselves.
    @ViewBuilder
    private var bottomPanel: some View {
        if showsRouteCard {
            routeCard
                .overlay(alignment: .topTrailing) {
                    controlsRow
                        .alignmentGuide(.top) { $0[.bottom] + attributionGap }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
        } else {
            controlsRow
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
        }
    }

    @ViewBuilder
    private var routeCard: some View {
        if let result = model.result {
            RouteSummaryCard(
                result: result,
                isReloading: model.isLoading,
                onStart: { startDrive(simulated: false) },
                onSimulate: { startDrive(simulated: true) },
                isPreview: !model.startsAtUserLocation,
                onDismiss: isDriving ? nil : Optional(clearRoute)
            )
        } else if model.isOutsideCoverage {
            coverageCard
        } else {
            loadingCard
        }
    }

    /// One glass cluster: the controls merge visually when they sit this close.
    private var controlsRow: some View {
        GlassEffectContainer(spacing: 12) {
            HStack(spacing: 12) {
                if model.isRiskGridAvailable {
                    heatmapToggle
                }
                recenterButton
            }
        }
    }

    private var recenterButton: some View {
        Button {
            recenterOnUser()
        } label: {
            Image(systemName: "location.fill")
                .font(.title3.weight(.semibold))
                .frame(width: 44, height: 44)
                .glassEffect(.regular.interactive(), in: .circle)
                .brandGlow(in: .circle)
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

    /// Shown instead of a route when the start or destination is outside the backend's pilot area.
    private var coverageCard: some View {
        HStack(spacing: 12) {
            Image(systemName: "map.fill")
                .font(.title2)
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("SafeRoute covers Austin for now")
                    .font(.headline)
                Text("Choose a start and destination in the Austin area.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .accessibilityElement(children: .combine)
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
            .brandGlow(in: .capsule)
        }
        .buttonStyle(.plain)
        .disabled(model.riskBands == nil)
        .accessibilityLabel(model.showsRiskHeatmap ? "Hide risk map" : "Show risk map")
    }

    // MARK: - Actions

    private func findRoute() {
        model.findRoute(
            from: locationManager.coordinate,
            avoiding: AvoidOptions(tolls: avoidTolls, highways: avoidHighways)
        )
    }

    /// Back to the neutral state: the search field's x and pulling the card down both land here.
    /// The card and the From / To panel leave first, which changes the map's insets; a camera change in
    /// that same update is applied by MapKit without animation, so the glide starts a moment later.
    private func clearRoute() {
        model.clearDestination()
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(80))
            recenterOnUser()
        }
    }

    /// Re-requests with the current profile and options if a route is showing or being fetched.
    private func refetchIfRouting() {
        if model.result != nil || model.isLoading {
            findRoute()
        }
    }

    private func toggleSelection(_ id: HazardCluster.ID) {
        selectedClusterID = selectedClusterID == id ? nil : id
    }

    // MARK: - Drive mode

    /// Drives the safe route of the current result. The screen stays awake until `endDrive()`; a real
    /// drive also switches location updates to navigation accuracy, a simulated one moves on its own.
    private func startDrive(simulated: Bool) {
        guard let result = model.result, let destination = model.destination else { return }
        isSearchFocused = false
        selectedClusterID = nil
        let drive = DriveModel(route: result.response.safest, destination: destination.location.coordinate, simulated: simulated)
        if !simulated {
            if let location = locationManager.location {
                drive.update(with: location)
            }
            locationManager.beginNavigationUpdates()
        }
        self.drive = drive
        UIApplication.shared.isIdleTimerDisabled = true
        if let camera = drive.camera {
            follow(camera)
        }
    }

    private func endDrive() {
        drive?.end()
        drive = nil
        car = nil
        locationManager.endNavigationUpdates()
        UIApplication.shared.isIdleTimerDisabled = false
        if let result = model.result {
            fitCamera(to: result)
        } else {
            recenterOnUser()
        }
    }

    /// Car-navigation framing: close in, tilted, turned to the route's direction, looking at a point ahead
    /// of the car so the car arrow sits in the lower third. Fixes arrive about once a second on a real drive
    /// and twice a second simulated; a linear move of the same length glides from one update into the next.
    /// The car arrow moves in the same transaction so it stays put on screen while the map slides under it.
    private func follow(_ camera: DriveCamera) {
        let animation: Animation = .linear(duration: drive?.isSimulated == true ? 0.5 : 1.0)
        withAnimation(animation) {
            car = drive?.car
            cameraHeading = camera.heading
            cameraPosition = .camera(MapCamera(centerCoordinate: camera.center, distance: 450, heading: camera.heading, pitch: 60))
        }
    }

    /// Animates back to the user. `.userLocation` only moves on a new fix, so a stationary phone
    /// would not budge; centering on the last known coordinate always animates.
    private func recenterOnUser() {
        withAnimation(.easeInOut(duration: 0.9)) {
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

#Preview {
    MapScreen(locationManager: LocationManager(), model: MapScreenModel())
}
