---
name: android-skill
description: Android apps (Gradle, Kotlin, APK): check the toolchain first, choose realistic options when building on a phone is impossible, build and read Gradle errors.
---
# Android skill

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
