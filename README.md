# ⚡ JINI AI Assistant — Android APK

A personal AI assistant for Android built with Kivy + KivyMD.

## Features
- 🎤 Voice recognition (Android SpeechRecognizer)
- 🔊 Text-to-Speech (Android TTS)
- 📱 App launcher (Chrome, WhatsApp, YouTube, etc.)
- 🔍 Web search / YouTube / Google
- 🔋 Battery, time, date, weather
- 📞 Contact search, call & WhatsApp
- 🔦 Flashlight, volume, WiFi, Bluetooth
- 💬 Full chat history screen

---

## 🚀 How to Build the APK (GitHub Actions — FREE)

### Step 1: Create a GitHub repository
1. Go to [github.com](https://github.com) and sign in (or create a free account)
2. Click **"New repository"** → name it `jini-android` → click **Create**

### Step 2: Upload these files
Upload all files from this folder to the repo:
- `main.py`
- `buildozer.spec`
- `.github/workflows/build_apk.yml`
- `README.md`

> **Tip:** You can drag-and-drop files directly on GitHub's web UI.

### Step 3: Trigger the build
- Go to your repo → click **"Actions"** tab
- Click **"Build JINI APK"** → click **"Run workflow"** → **"Run workflow"**
- Wait ~25–35 minutes ☕

### Step 4: Download your APK
- When the build is ✅ green, click on the workflow run
- Scroll down to **"Artifacts"** section
- Click **"JINI-APK"** to download the zip
- Unzip it → you'll find `jini-debug.apk`

### Step 5: Install on your Android phone
1. Transfer the APK to your phone (email, USB, Google Drive, etc.)
2. Open it on your phone
3. Allow "Install from unknown sources" if prompted
4. Done! 🎉

---

## 📋 Requirements
- Free GitHub account
- Android phone (Android 5.0+)
- ~35 min build time on first run (subsequent builds are cached, ~10 min)
