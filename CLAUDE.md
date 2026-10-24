# SafeRoute — CLAUDE.md

24-hour HackTX hackathon project. Three people work in this repo. Read this whole file before touching code.

## What the app is

An iOS navigation app that finds the **safest** driving route rather than the fastest, for new/teen drivers, elderly drivers, and drivers carrying sensitive passengers (pregnant, injured, infants). Google Maps minimizes time; we minimize expected risk subject to a detour budget. Pilot area is Austin, TX.

## How "safe" is defined (backend does this; the app only displays it)

A separate Python backend asks a routing engine for several alternative routes, then scores each one against:
- historical crash density (Austin Vision Zero data)
- dangerous maneuvers (unprotected left turns, highway merges, roundabouts, U-turns)
- road characteristics (speed limit, lanes, lighting)
- for sensitive passengers, ride comfort (rough surface, sharp curves)

Each profile has different weights. The backend returns the fastest route and the safest route that is at most ~25% longer, plus a comparison.

Three profiles, exact wire strings: `"teen"`, `"elderly"`, `"sensitive_passenger"` (see `Models/Profile.swift`).

## Tech constraints (non-negotiable)

- Xcode project, SwiftUI, **iOS 26 minimum deployment target**, Swift only. iOS 26 APIs are fine; no availability checks needed.
- **MapKit only** for maps, search (`MKLocalSearch`), location (`CoreLocation`), and polylines (`MapPolyline`). No third-party packages, no SPM dependencies, no CocoaPods.
- Bundle ID is `com.hacktx.SafeRoute`. The project already builds and runs on a physical iPhone.
- **Never modify signing, build settings, the `.pbxproj`, or anything under Signing & Capabilities.** Only add or edit Swift files, and Info.plist keys when a feature requires it.
- **Liquid Glass:** apply `.glassEffect()` to the route summary card and primary buttons only. Never on list rows or map content.
- Keep every change small and self-contained so it can be built and committed after each one.
- Use `@Observable` for view models.

## Project facts discovered from the repo (keep in sync)

- The target's sources are a **synchronized folder group** (`PBXFileSystemSynchronizedRootGroup` → `SafeRoute/`). Any file created anywhere under `SafeRoute/` is automatically part of the target. Adding files never requires editing the `.pbxproj`.
- `GENERATE_INFOPLIST_FILE = YES` and no `INFOPLIST_FILE`: the Info.plist is generated purely from `INFOPLIST_KEY_*` build settings. **Do not add an `Info.plist` file under `SafeRoute/`**: the synchronized folder copies it as a resource and the build fails with "Multiple commands produce Info.plist" (verified). Any new plist key is therefore a build-setting change, which the project owner makes by hand in Xcode: target SafeRoute -> Info tab -> "Custom iOS Target Properties" -> +. Claude only names the key and the value to paste.
- Swift settings: language mode 5, `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`, `SWIFT_APPROACHABLE_CONCURRENCY = YES`. Consequences:
  - Every type is `@MainActor` unless marked `nonisolated`. Mark pure data types (`Config`, `Profile`, `Mocks`, Codable models) `nonisolated` so they can be used from any context.
  - Framework delegate callbacks (e.g. `CLLocationManagerDelegate`) must be declared `nonisolated` and hop back with `Task { @MainActor in ... }`.
- Toolchain on this Mac: Xcode 26.3 (17C529) is the selected `xcodebuild`. Connected test device: "Sihan's iPhone", id `00008140-000445E62893C01C`, running iOS 27.0.1.

### Build command (run after every change, fix all errors before reporting)

```sh
xcodebuild -project SafeRoute.xcodeproj -scheme SafeRoute \
  -destination 'id=00008140-000445E62893C01C' -allowProvisioningUpdates build 2>&1 \
  | grep -E "error:|warning:|BUILD (SUCCEEDED|FAILED)"
```

If the phone is not plugged in, fall back to `-destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO` to at least compile.

## Backend API contract

Base URL is a single constant in `Config.swift`. Placeholder: `"https://REPLACE-ME.ngrok-free.app"`. It gets swapped for the real ngrok URL when the backend person provides it.

### POST /route

Request JSON:
```json
{
  "origin": {"lat": 30.2849, "lon": -97.7341},
  "destination": {"lat": 30.2672, "lon": -97.7431},
  "profile": "teen"
}
```
Response JSON:
```json
{
  "fastest": {"polyline": [[30.2849,-97.7341], ...], "minutes": 14.2, "miles": 5.1, "risk": 0.71},
  "safest":  {"polyline": [[30.2849,-97.7341], ...], "minutes": 18.0, "miles": 6.0, "risk": 0.44},
  "delta_minutes": 3.8,
  "risk_reduction_pct": 38,
  "hazards_avoided": ["2 unprotected left turns", "I-35 merge", "high-crash zone on Lamar Blvd"]
}
```
Polyline points are `[lat, lon]` pairs.

### GET /risk

Returns a GeoJSON FeatureCollection of polygons, each with a property `"risk"` from 0 to 1 (used for the heatmap overlay).

### Mock fallback rule

The backend may not exist yet. **Always** fall back to the hardcoded mock response in `Mocks/Mocks.swift` when the request fails or `Config.baseURL` still contains `REPLACE-ME`, so the UI is demoable at all times. The mock is realistic: two different polylines through central Austin (UT campus → downtown) with 20+ points each. `Mocks.routeResponseJSON` is raw JSON `Data` so it goes through the same decoder as a real response.

## Architecture

```
SafeRoute/
  App/        SafeRouteApp.swift, ContentView.swift
  Models/     Route.swift, RouteResponse.swift (Codable), Profile.swift (enum: display name + SF Symbol)
  Services/   RouteService.swift (URLSession, async/await), LocationManager.swift, SearchService.swift (MKLocalSearch)
  Views/      MapScreen.swift, SearchBar.swift, ProfilePicker.swift, RouteSummaryCard.swift
  Mocks/      Mocks.swift
  Config.swift
```

## Working rules

- After writing code, build for the connected iPhone destination and fix any errors before reporting back.
- Report in 3 to 5 lines: what was added, what to test on the phone, anything that must be done manually.
- Do not add features that weren't asked for. Do not refactor existing code unless needed for the current step.
- If something needs an Info.plist key, do not create a plist file (see above). Report the exact key name and value for the owner to add in Xcode's Info tab.
- Do not start a later step until told to.

## Build plan

- [x] **Step 1:** Full-screen Map centered on the user's location with the blue location dot, plus a search bar at the top using MKLocalSearch to pick a destination. Tapping a result drops a pin and stores the destination coordinate. `NSLocationWhenInUseUsageDescription` must be added by the owner in Xcode's Info tab (see project facts). Folder structure, `Config.swift`, `Profile.swift`, `Mocks.swift` created.
- [ ] **Step 2:** `RouteService` calling POST /route with Codable models, mock fallback, and a "Find safest route" button that triggers it once origin (user location) and destination are set.
- [ ] **Step 3:** Draw fastest and safest as `MapPolyline`s in different colors (gray for fastest, green for safest), and a bottom glass card showing delta minutes, risk reduction %, and the hazards avoided. Add the `ProfilePicker` as a segmented control above the card.
- [ ] **Step 4:** Risk heatmap toggle that fetches GET /risk and renders polygons with `MapPolygon` colored by risk.
- [ ] **Step 5:** Polish: animations when routes appear, dark mode check, SF Symbols for each profile, a small legend.
