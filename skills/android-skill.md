---
name: android-skill
description: Android apps (Gradle, Kotlin, APK): check the toolchain first, choose realistic options when building on a phone is impossible, build and read Gradle errors.
---
# Android skill

## Quick rules (read first)
1. Check what the device can really build (JDK, Gradle, Android SDK) before promising an APK. On Termux a full Gradle build often needs the SDK installed first.
2. Start from the smallest working app: one activity, one screen, one visible result. Add features one at a time and build after each.
3. Ask for the fewest permissions, and only when the feature needs them. Explain why in the UI.
4. Never do network or disk work on the main thread. Use coroutines or a background executor.
5. Keep versions in one place (`gradle/libs.versions.toml` or the top of `build.gradle`) and do not guess library versions: look them up.
6. Read the build error from the first `error:` line, not the last line.

## Safety in this skill
- Do not build apps that hide their icon, record the screen, calls or microphone secretly, read other apps' messages or one-time codes, draw invisible overlays, or abuse accessibility services to click for the user. These are stalkerware and fraud patterns.
- Parental-control or device-management apps are fine when they are visible, installed by the device owner and clearly say what they monitor.

## 1. Inspect before you promise anything
```
java -version; gradle -v; echo $ANDROID_HOME; which adb sdkmanager aapt2; df -h .; free -m
```
Building Android natively on a phone is heavy (Gradle + SDK + 2 to 4 GB RAM) and often unsupported. Say so plainly and offer the realistic options:
1. **A web app / PWA** (`use_template web-app`) that the user installs from the browser ("Add to home screen"). Best default for simple apps and games.
2. **A complete Gradle project** the user builds on a PC or CI, with a README that has the exact command.
3. **Native build here** only when java, gradle and the SDK exist and RAM is sufficient.

## 2. Project skeleton (Kotlin, single activity)
```
app/build.gradle.kts            plugins, compileSdk 34, minSdk 24, dependencies
app/src/main/AndroidManifest.xml
app/src/main/java/com/example/app/MainActivity.kt
app/src/main/res/layout/activity_main.xml
app/src/main/res/values/{strings,themes}.xml
settings.gradle.kts, build.gradle.kts, gradle.properties, gradlew + gradle/wrapper
```
Keep AGP, Kotlin and Gradle versions compatible (check the AGP release notes). Use ViewBinding or Compose, not both. Declare every permission in the manifest and request dangerous ones at runtime.

## 3. Build
`./gradlew assembleDebug --no-daemon` with `run_shell(timeout=1800)`. Read the END of the log for the real error. APK appears in `app/build/outputs/apk/debug/`; report its path and size.

## Troubleshooting
| Error | Fix |
|---|---|
| `SDK location not found` | `local.properties`: `sdk.dir=/path/to/sdk` |
| `Unsupported class file major version` | JDK too new/old for this Gradle; use the JDK the project needs (17 for current AGP) |
| `Could not resolve ...` | Offline or missing repository: add `google()` and `mavenCentral()` |
| `aapt2` crashes on ARM | Use a build tool matching the architecture; build on a PC instead |
| Out of memory | `org.gradle.jvmargs=-Xmx1536m` in gradle.properties, `--no-daemon` |

## Good and bad examples

### 1. Permissions
Bad: ask for everything at install time.
```xml
<uses-permission android:name="android.permission.READ_SMS"/>
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
```
Good: declare only what the feature needs, and ask at the moment it is used.
```xml
<uses-permission android:name="android.permission.INTERNET"/>
```

### 2. Work off the main thread
Bad: a network call inside `onCreate` freezes the screen and crashes with `NetworkOnMainThreadException`.
Good:
```kotlin
lifecycleScope.launch {
    val text = withContext(Dispatchers.IO) { URL(url).readText() }
    textView.text = text
}
```

### 3. Reporting a build
Bad: "The app is finished." (nothing was built)
Good: "Built with `./gradlew assembleDebug`; the APK is at `app/build/outputs/apk/debug/app-debug.apk`." If the build could not run, say so and give the exact command for the user to run.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Version mismatch between Gradle, the Android plugin and Kotlin | Check the compatibility table for the plugin version; change one version at a time |
| `Unresolved reference` after adding a library | Add the dependency in `build.gradle`, sync, and import the right package |
| App crashes at start with no message | Run `adb logcat` or read the stack trace for the first `Caused by:` |
| Layout cut off on small phones | Use `ConstraintLayout`, `dp`, and test a 360dp-wide screen |
| Data lost on rotation | Keep state in a `ViewModel` or save it in `onSaveInstanceState` |
| Cleartext HTTP blocked | Use HTTPS; do not turn cleartext on for the whole app |

## Checklist before you finish
- [ ] The build command was run and its result is reported honestly.
- [ ] Only needed permissions are in the manifest.
- [ ] No network or disk work on the main thread.
- [ ] The app was checked on a small screen and after rotation.
- [ ] Nothing in the app hides itself or collects data the user was not told about.
