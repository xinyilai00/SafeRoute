# SafeRoute iOS app — CLAUDE.md

Rules for the iOS app in this folder and `SafeRoute.xcodeproj`. Read the root `CLAUDE.md` first for the product, the team, and the API contract. Owner: Nick. Only Nick commits Xcode changes.

## Tech constraints (non-negotiable)

- Xcode project, SwiftUI, **iOS 26 minimum deployment target**, Swift only. iOS 26 APIs are fine; no availability checks needed.
- **MapKit only** for maps, search (`MKLocalSearch`), location (`CoreLocation`), and polylines (`MapPolyline`). No third-party packages, no SPM dependencies, no CocoaPods.
- Bundle ID is `com.hacktx.SafeRoute`. The project already builds and runs on a physical iPhone.
- **Never modify signing, build settings, the `.pbxproj`, or anything under Signing & Capabilities.** Only add or edit Swift files.
- **Liquid Glass:** `.glassEffect()` / `.buttonStyle(.glass)` on the summary and loading cards, the primary round buttons (profile, map style, recenter, Risk map), and the search field and its suggestion-list container. Never on list rows or map content. Buttons that sit together go in one `GlassEffectContainer`.
- Keep every change small and self-contained so it can be built and committed after each one.
- Use `@Observable` for view models.

## Project facts discovered from the repo (keep in sync)

- The target's sources are a **synchronized folder group** (`PBXFileSystemSynchronizedRootGroup` → `SafeRoute/`). Any file created anywhere under `SafeRoute/` is automatically part of the target. Adding files never requires editing the `.pbxproj`.
- `GENERATE_INFOPLIST_FILE = YES` and no `INFOPLIST_FILE`: the Info.plist is generated purely from `INFOPLIST_KEY_*` build settings. `INFOPLIST_KEY_NSLocationWhenInUseUsageDescription` is already set (the owner added it in Xcode's Info tab). **Do not add an `Info.plist` file under `SafeRoute/`**: the synchronized folder copies it as a resource and the build fails with "Multiple commands produce Info.plist" (verified). Any new plist key is a build-setting change the owner makes by hand: target SafeRoute → Info tab → "Custom iOS Target Properties" → +. Claude only names the key and the value to paste.
- Swift settings: language mode 5, `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`, `SWIFT_APPROACHABLE_CONCURRENCY = YES`. Consequences:
  - Every type is `@MainActor` unless marked `nonisolated`. Mark pure data types (`Config`, `Profile`, `Mocks`, Codable models) `nonisolated` so they can be used from any context.
  - Framework delegate callbacks (e.g. `CLLocationManagerDelegate`) must be declared `nonisolated` and hop back with `Task { @MainActor in ... }`.
- iOS 26 MapKit: use `MKMapItem.location` and `MKMapItem.address` (`placemark` is deprecated).
- Camera framing: the bottom panel (picker, button or card) is a `.safeAreaInset(edge: .bottom)` on the `Map`, and a clear 64pt `.safeAreaInset(edge: .top)` reserves the search field's space, so `MapCameraPosition.rect` fits routes inside the visible map. The `SearchBar` itself stays a ZStack overlay so its dropdown never shifts the camera.
- `RouteService` is the only place that talks to the network; it returns `RouteResult` (`response` + `isDemoData`). `isDemoData` drives the "Demo data" badge on the card.
- Toolchain on this Mac: Xcode 26.3 (17C529) is the selected `xcodebuild`. Connected test device: "Sihan's iPhone", id `00008140-000445E62893C01C`, running iOS 27.0.1.

### Build command (run after every change, fix all errors before reporting)

```sh
xcodebuild -project SafeRoute.xcodeproj -scheme SafeRoute \
  -destination 'id=00008140-000445E62893C01C' -allowProvisioningUpdates build 2>&1 \
  | grep -E "error:|warning:|BUILD (SUCCEEDED|FAILED)"
```

If the phone is not plugged in, fall back to `-destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO` to at least compile. The `appintentsmetadataprocessor` warning is noise.

## Talking to the backend

The contract itself is in the root `CLAUDE.md`. App-side rules:

- Base URL is a single constant in `Config.swift`, currently Xinyi's ngrok tunnel (`data/app.py` on this branch of her work). The URL changes whenever ngrok restarts; get the new one from the team chat and update only that constant. If it contains `REPLACE-ME` the app runs on mocks.
- **Mock fallback rule:** the backend may not exist yet. **Always** fall back to the hardcoded mock response in `Mocks/Mocks.swift` when the request fails or `Config.baseURL` still contains `REPLACE-ME`, so the UI is demoable at all times. The mock matches the contract exactly: UT campus → downtown, two different polylines with 20+ `[lat, lng]` points each, 2 to 3 `risk_events` per route placed on real polyline points. `Mocks.routeResponseJSON(for: profile)` returns raw JSON `Data` so it goes through the same decoder as a real response. Geometry, ETA and distance are identical across profiles; scores, hazards and the comparison differ per profile (teen: I-35 merge and high-speed arterial; elderly: unprotected left turns; sensitive_passenger: rough pavement and sharp curves) so switching profiles is visibly different. The placeholder-URL path sleeps 0.7 s before returning the mock so the loading state is visible; the network-failure fallback does not.
- Request: `origin` and `destination` are `{"lat", "lng"}` (note `lng`, not `lon`). Send `"safety_weight": 1.0` for now; a slider may come in Step 5. `avoid` is the list of road types the driver turned off in the route options menu (`"highways"`, `"tolls"`; empty by default, meaning both are allowed). It is a strong preference, not a ban, and the backend says in `comparison.summary` when it could not honor it.
- Coordinates: `geometry` is `[lat, lng]`, so pair `[0]` is latitude. GET /risk is GeoJSON, which is `[lng, lat]`, so flip when building polygon coordinates.
- Heatmap: `RiskService` calls `GET /risk?min_risk=<Config.riskMinimum>` once per launch, decodes only `features[].properties.risk`, `ix`, `iy` and `features[].geometry` (unknown keys such as the top-level `grid` are ignored), flips `[lng, lat]`, then `RiskHeatmap.bands` buckets cells into 5 color bands and merges neighbouring same-band cells into rectangles (using the server's optional `ix`/`iy`; cells without them stay single). The result is cached in `MapScreenModel` and drawn by `RiskHeatmapLayer`, a custom `MapContent` that takes only the precomputed bands, so route/profile changes do no per-cell work. Every `MapPolygon` is a separate MapKit overlay, so polygon count is what matters for smoothness: counts per threshold are next to `Config.riskMinimum` (0.5 now). No mock: on failure the "Risk map" toggle is hidden.
- Backend errors: `/route` returns 404 (no route), 422 (bad profile / `safety_weight`), 502 (engine down); any non-2xx falls back to mocks. Both services send `ngrok-skip-browser-warning: true`; `/route` times out after 10 s, `/risk` after 20 s.
- UI behaviour (polish round 1): picking a search result requests the route immediately (no button); the bottom card shows a loading state first. The profile is a circular glass `Menu` button under the search field, persisted with `@AppStorage(Config.profileStorageKey)`; changing it re-requests the current route. Markers: `high_crash_zone` events are never drawn (the heatmap covers them); the fastest route's maneuvers are small gray markers under the safest route's colored ones; tapping a marker toggles a description bubble. When `fastest.geometry == safest.geometry` the gray line and its markers are hidden and the card says "Fastest route is already the safest". The card's added minutes are computed from the rounded ETAs it displays, not from `minutes_added`. Search: focus lives in `MapScreen` so a map tap dismisses the keyboard; the results list is a `ScrollView` with `.scrollDismissesKeyboard(.immediately)`; Cancel closes the results and keeps the text.
- UI behaviour (polish round 2): search uses `MKLocalSearchCompleter` (addresses + points of interest, biased to the user or Austin); tapping a suggestion resolves it with `MKLocalSearch(request: .init(completion:))`; matched text is bolded and a keyword heuristic picks the row symbol. The x button calls `MapScreenModel.clearDestination()` and recenters. Map style (Standard / Satellite / Hybrid / Muted) is `MapStyleChoice`, stored with `@AppStorage(Config.mapStyleStorageKey)`; both route lines have white casings so they read on imagery. The recenter button is a custom glass button (`MapUserLocationButton` and `mapScope` were removed).
- Card (polish round 3): plain words first. Header "Safer Route" + green added-time badge (from rounded ETAs; "same time" under a minute), a sentence from `RouteResponse.avoidanceSentence` (counts of `risk_events` by type the safest has fewer of, via `RiskEventType.friendlyName(count:)`; falls back to `comparison.summary`), two rows (Safe / Fastest: ETA + 5-dot meter relative to the higher `risk_score`), "What you avoid" chips from `avoidedHazards`, and a Details disclosure holding miles, risk reduction % and the Demo data badge. Identical routes: "Fastest is already the safest" card without rows. On-map labels (`RouteLabels.swift`) sit where the two polylines are farthest apart. All controls are 44 pt `.glassEffect(.regular.interactive())` circles/capsules for uniform height. Recenter centers on the last known coordinate because `.userLocation` only moves on a new fix.
- Display: distances in **miles**, converted from `distance_km` (× 0.621371). `risk_score` is penalty points, lower is safer; show the comparison (`minutes_added`, `risk_reduction_pct`, `summary`) rather than raw scores.

## Architecture

```
SafeRoute/
  App/        SafeRouteApp.swift, ContentView.swift
  Models/     Route.swift, RouteResponse.swift (Codable), RiskGrid.swift (GeoJSON -> RiskCell), Profile.swift (enum: display name + SF Symbol)
  Services/   RouteService.swift (POST /route), RiskService.swift (GET /risk), LocationManager.swift, SearchService.swift (MKLocalSearch)
  Views/      MapScreen.swift, MapScreenModel.swift (@Observable screen state), RiskHeatmapLayer.swift (MapContent), SearchBar.swift, ProfilePicker.swift (glass menu button), MapStyleMenu.swift (glass menu button + MapStyleChoice), RouteOptionsMenu.swift (glass menu: Highways / Toll roads toggles, both on by default; unchecked ones are sent as `avoid`), RouteSummaryCard.swift, RouteLabels.swift (on-map "Safe · 24 min" capsules + placement)
  Mocks/      Mocks.swift
  Config.swift
```

## Working rules

- After writing code, build for the connected iPhone destination and fix any errors before reporting back.
- Report in 3 to 5 lines: what was added, what to test on the phone, anything that must be done manually.
- Do not add features that weren't asked for. Do not refactor existing code unless needed for the current step.
- If something needs an Info.plist key, do not create a plist file (see project facts). Report the exact key name and value for the owner to add in Xcode's Info tab.
- Do not start a later step until told to.

## Build plan

- [x] **Step 1:** Full-screen Map centered on the user's location with the blue location dot, plus a search bar at the top using MKLocalSearch to pick a destination. Tapping a result drops a pin and stores the destination coordinate. Folder structure, `Config.swift`, `Profile.swift`, `Mocks.swift` created. Location permission key added by the owner.
- [x] **Step 2:** `RouteService` calling POST /route with Codable models: request `{origin: {lat, lng}, destination: {lat, lng}, profile, safety_weight: 1.0}`, response `fastest` / `safest` (`geometry`, `eta_minutes`, `distance_km`, `risk_score`, `risk_events[]`) and `comparison` (`minutes_added`, `risk_reduction_pct`, `summary`). Mock fallback per the rule above, and a "Find safest route" button that triggers it once origin (user location) and destination are set.
- [x] **Step 3:** Draw `fastest.geometry` and `safest.geometry` as `MapPolyline`s in different colors (gray for fastest, green for safest). Show `safest.risk_events` as small markers on the map at their `lat`/`lng`, with a symbol per `type`. Bottom glass card showing `comparison.minutes_added`, `comparison.risk_reduction_pct`, `comparison.summary`, and each route's ETA and distance in miles (converted from `distance_km`). Add the `ProfilePicker` as a segmented control above the card.
- [x] **Step 4:** Risk heatmap toggle that fetches GET /risk and renders each polygon with `MapPolygon` colored by `properties.risk` (0 to 1). Flip GeoJSON `[lng, lat]` to coordinates.
- [ ] **Step 5:** Polish: animations when routes appear, dark mode check, SF Symbols for each profile and each `risk_events` type, a small legend. Possibly a `safety_weight` slider (0 = fastest, 1 = safest; fixed at 1.0 until then). Starting points: commit `b5c6625` (replaced by the Step 4 merge) contains a `HeatmapLegend` and a `SafetySlider` in `HeatmapControls.swift`; copy from git history rather than re-merging it.
