[app]

# App title — shown on home screen
title = JINI AI Assistant

# Package name — must be unique, reverse-domain style
package.name = jini

# Package domain
package.domain = com.yourname

# Source directory (where main.py lives)
source.dir = .

# Source files to include
source.include_exts = py,png,jpg,kv,atlas,json,ttf

# App version
version = 1.0

# Python requirements
requirements = python3,kivy==2.3.0,kivymd,requests,urllib3,certifi

# Orientation
orientation = portrait

# Minimum Android API
android.minapi = 21

# Target Android API
android.api = 33

# NDK version
android.ndk = 25b

# Android permissions
android.permissions = INTERNET,RECORD_AUDIO,READ_CONTACTS,CALL_PHONE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_FINE_LOCATION,CAMERA,VIBRATE,FLASHLIGHT,CHANGE_WIFI_STATE,ACCESS_WIFI_STATE,BLUETOOTH,BLUETOOTH_ADMIN,MODIFY_AUDIO_SETTINGS,RECEIVE_BOOT_COMPLETED

# Android features
android.features = android.hardware.microphone,android.hardware.camera

# App icon (place icon.png in the root folder, 512×512 px)
# icon.filename = %(source.dir)s/assets/icon.png

# Presplash (place presplash.png in the root folder)
# presplash.filename = %(source.dir)s/assets/presplash.png

# Fullscreen
fullscreen = 0

# Android architecture
android.archs = arm64-v8a, armeabi-v7a

# Gradle dependencies for Speech recognition, TTS, etc.
# (these are built into Android SDK — no extra gradle lines needed)

# Log level
log_level = 2

# Warn on missing modules
warn_on_root = 1

[buildozer]

# Buildozer log level
log_level = 2

# Warn on root
warn_on_root = 1
