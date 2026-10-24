# SafeRoute iOS app — CLAUDE.md

Rules for the iOS app in this folder and `SafeRoute.xcodeproj`. Read the root `CLAUDE.md` first for the product, the team, and the API contract. Owner: Nick. Only Nick commits Xcode changes.

## Tech constraints (non-negotiable)

- Xcode project, SwiftUI, **iOS 26 minimum deployment target**, Swift only. iOS 26 APIs are fine; no availability checks needed.
- **MapKit only** for maps, search (`MKLocalSearch`), location (`CoreLocation`), and polylines (`MapPolyline`). No third-party packages, no SPM dependencies, no CocoaPods.
- Bundle ID is `com.hacktx.SafeRoute`. The project already builds and runs on a physical iPhone.
- **Never modify signing, build settings, the `.pbxproj`, or anything under Signing & Capabilities.** Only add or edit Swift files.
- **Liquid Glass:** apply `.glassEffect()` to the route summary card and primary buttons only. Never on list rows or map content.
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
- Request: `origin` and `destination` are `{"lat", "lng"}` (note `lng`, not `lon`). Send `"safety_weight": 1.0` for now; a slider may come in Step 5.
- Coordinates: `geometry` is `[lat, lng]`, so pair `[0]` is latitude. GET /risk is GeoJSON, which is `[lng, lat]`, so flip when building polygon coordinates.
- Heatmap: `RiskService` calls `GET /risk?min_risk=<Config.riskMinimum>` once per launch (cached in `MapScreenModel`), decodes only `features[].properties.risk` and `features[].geometry` (unknown keys such as the top-level `grid` are ignored), flips `[lng, lat]`, and draws each cell as a `MapPolygon` from yellow to red. No mock: on failure the "Risk map" toggle is hidden. Cell counts per threshold are noted next to `Config.riskMinimum`; raise it if the device stutters.
- Backend errors: `/route` returns 404 (no route), 422 (bad profile / `safety_weight`), 502 (engine down); any non-2xx falls back to mocks. Both services send `ngrok-skip-browser-warning: true`; `/route` times out after 10 s, `/risk` after 20 s.
- Display: distances in **miles**, converted from `distance_km` (× 0.621371). `risk_score` is penalty points, lower is safer; show the comparison (`minutes_added`, `risk_reduction_pct`, `summary`) rather than raw scores.

## Architecture

```
SafeRoute/
  App/        SafeRouteApp.swift, ContentView.swift
  Models/     Route.swift, RouteResponse.swift (Codable), RiskGrid.swift (GeoJSON -> RiskCell), Profile.swift (enum: display name + SF Symbol)
  Services/   RouteService.swift (POST /route), RiskService.swift (GET /risk), LocationManager.swift, SearchService.swift (MKLocalSearch)
  Views/      MapScreen.swift, MapScreenModel.swift (@Observable screen state), SearchBar.swift, ProfilePicker.swift, RouteSummaryCard.swift
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
