"""
JINI v1.0 — Android AI Personal Assistant
Ported from JINI v6 (Windows) to Android via Kivy + KivyMD
Features:
  • Voice recognition (Android SpeechRecognizer)
  • Text-to-Speech (Android TTS)
  • App launcher (open installed apps)
  • Web search / YouTube / Google
  • Battery, time, date, weather
  • Contact search & call / WhatsApp
  • Flashlight, volume, brightness, WiFi, Bluetooth
  • Notifications
  • Wake-word detection ("Hey JINI")
  • Animated orb + mini popup overlay
  • Full chat history screen
"""

import os, re, threading, json, time
from datetime import datetime
from pathlib import Path

# ── Kivy setup (must be before any kivy imports) ──────────────────────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.clock import Clock, mainthread
from kivy.metrics import dp, sp
from kivy.animation import Animation
from kivy.properties import StringProperty, ColorProperty, BooleanProperty, NumericProperty
from kivy.graphics import Color, RoundedRectangle, Rectangle, Ellipse, Line
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

# ── Android detection ─────────────────────────────────────────────────────────
try:
    from android.permissions import request_permissions, Permission, check_permission
    from android.runnable import run_on_ui_thread
    from jnius import autoclass, cast, PythonJavaClass, java_method
    IS_ANDROID = True
    # Android Java classes
    PythonActivity     = autoclass('org.kivy.android.PythonActivity')
    Intent             = autoclass('android.content.Intent')
    Uri                = autoclass('android.net.Uri')
    Settings           = autoclass('android.provider.Settings')
    AudioManager       = autoclass('android.media.AudioManager')
    BatteryManager     = autoclass('android.os.BatteryManager')
    WifiManager        = autoclass('android.net.wifi.WifiManager')
    BluetoothAdapter   = autoclass('android.bluetooth.BluetoothAdapter')
    SpeechRecognizer   = autoclass('android.speech.SpeechRecognizer')
    RecognizerIntent   = autoclass('android.speech.RecognizerIntent')
    TextToSpeech       = autoclass('android.speech.tts.TextToSpeech')
    Locale             = autoclass('java.util.Locale')
    Camera             = autoclass('android.hardware.Camera')
    PackageManager     = autoclass('android.content.pm.PackageManager')
    ContactsContract   = autoclass('android.provider.ContactsContract')
    MediaStore         = autoclass('android.provider.MediaStore')
    NotificationManager= autoclass('android.app.NotificationManager')
    Build              = autoclass('android.os.Build')
    Environment        = autoclass('android.os.Environment')
    context            = PythonActivity.mActivity
except Exception:
    IS_ANDROID = False
    context    = None

# ── Colour palette (matches JINI desktop) ────────────────────────────────────
C = {
    "bg":       get_color_from_hex("#F0F4FF"),
    "bg2":      get_color_from_hex("#FFFFFF"),
    "bg3":      get_color_from_hex("#E8EDF8"),
    "border":   get_color_from_hex("#D8E0F0"),
    "accent":   get_color_from_hex("#4A90E2"),
    "accent2":  get_color_from_hex("#5BA0F2"),
    "green":    get_color_from_hex("#34C759"),
    "red":      get_color_from_hex("#FF3B30"),
    "yellow":   get_color_from_hex("#FF9500"),
    "text":     get_color_from_hex("#1A1A2E"),
    "text2":    get_color_from_hex("#4A5568"),
    "text3":    get_color_from_hex("#9AA5BE"),
    "white":    get_color_from_hex("#FFFFFF"),
}

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / ".jini_android_config.json"

def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f: return json.load(f)
        except: pass
    return {}

def save_config(data):
    try:
        with open(CONFIG_PATH, "w") as f: json.dump(data, f, indent=2)
    except: pass

# ─────────────────────────────────────────────────────────────────────────────
#  TTS — Android native or pyttsx3 fallback
# ─────────────────────────────────────────────────────────────────────────────
class TTSEngine:
    def __init__(self):
        self._tts = None
        self._ready = False
        if IS_ANDROID:
            self._init_android()
        else:
            self._init_desktop()

    def _init_android(self):
        try:
            class OnInitListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
                def __init__(self, callback):
                    super().__init__(); self.cb = callback
                @java_method('(I)V')
                def onInit(self, status):
                    self.cb(status == 0)

            listener = OnInitListener(self._on_init)
            self._tts = TextToSpeech(context, listener)
        except Exception as e:
            print(f"TTS init error: {e}")

    def _on_init(self, success):
        self._ready = success
        if success and self._tts:
            try:
                self._tts.setLanguage(Locale.US)
                self._tts.setPitch(1.0)
                self._tts.setSpeechRate(0.9)
            except: pass

    def _init_desktop(self):
        try:
            import pyttsx3
            self._eng = pyttsx3.init()
            self._eng.setProperty("rate", 175)
            self._ready = True
        except: self._eng = None

    def speak(self, text):
        if not text: return
        threading.Thread(target=self._speak_bg, args=(str(text)[:300],), daemon=True).start()

    def _speak_bg(self, text):
        try:
            if IS_ANDROID and self._tts and self._ready:
                self._tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, "jini_utt")
            elif hasattr(self, "_eng") and self._eng:
                self._eng.say(text); self._eng.runAndWait()
        except: pass

    def stop(self):
        try:
            if IS_ANDROID and self._tts: self._tts.stop()
            elif hasattr(self, "_eng") and self._eng: self._eng.stop()
        except: pass


# ─────────────────────────────────────────────────────────────────────────────
#  Speech Recogniser — Android native
# ─────────────────────────────────────────────────────────────────────────────
class VoiceRecogniser:
    def __init__(self, on_result, on_error, on_start):
        self.on_result = on_result
        self.on_error  = on_error
        self.on_start  = on_start
        self._recognizer = None
        self._listening  = False
        if IS_ANDROID:
            self._setup_android()

    def _setup_android(self):
        try:
            class RecognitionListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/RecognitionListener']
                def __init__(self, outer): super().__init__(); self.outer = outer
                @java_method('(I)V')
                def onError(self, error):
                    self.outer._listening = False
                    msgs = {1:"Network error",2:"Network error",3:"No audio",
                            4:"Server error",5:"Client error",6:"Speech timeout",
                            7:"No match",8:"RecognitionService busy",9:"Insufficient permissions"}
                    self.outer.on_error(msgs.get(error, f"Error {error}"))
                @java_method('(Landroid/os/Bundle;)V')
                def onResults(self, results):
                    self.outer._listening = False
                    matches = results.getStringArrayList(RecognizerIntent.EXTRA_RESULTS)
                    if matches and matches.size() > 0:
                        self.outer.on_result(matches.get(0))
                    else:
                        self.outer.on_error("No match")
                @java_method('(I)V')
                def onReadyForSpeech(self, params): self.outer.on_start()
                @java_method('()V')
                def onEndOfSpeech(self): pass
                @java_method('(Landroid/os/Bundle;)V')
                def onBeginningOfSpeech(self, params): pass
                @java_method('([B)V')
                def onBufferReceived(self, buf): pass
                @java_method('(FLandroid/os/Bundle;)V')
                def onPartialResults(self, rmslevel, results): pass
                @java_method('(Landroid/os/Bundle;)V')
                def onEvent(self, eventType, params): pass
                @java_method('(F)V')
                def onRmsChanged(self, rms): pass

            self._listener   = RecognitionListener(self)
            self._recognizer = SpeechRecognizer.createSpeechRecognizer(context)
            self._recognizer.setRecognitionListener(self._listener)
        except Exception as e:
            print(f"Voice init error: {e}")

    @run_on_ui_thread
    def start_listening(self):
        if self._listening: return
        if not IS_ANDROID:
            self.on_error("Voice only available on Android"); return
        try:
            self._listening = True
            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1500)
            self._recognizer.startListening(intent)
        except Exception as e:
            self._listening = False
            self.on_error(str(e))

    @run_on_ui_thread
    def stop_listening(self):
        self._listening = False
        try:
            if self._recognizer: self._recognizer.stopListening()
        except: pass


# ─────────────────────────────────────────────────────────────────────────────
#  Android Helpers
# ─────────────────────────────────────────────────────────────────────────────
class AndroidHelper:
    @staticmethod
    def open_app(package_name):
        if not IS_ANDROID: return f"Would open: {package_name}"
        try:
            pm = context.getPackageManager()
            launch_intent = pm.getLaunchIntentForPackage(package_name)
            if launch_intent:
                context.startActivity(launch_intent)
                return f"Opening {package_name.split('.')[-1].capitalize()}"
            return f"App '{package_name}' not installed"
        except Exception as e: return f"Error: {e}"

    @staticmethod
    def open_url(url):
        if not IS_ANDROID:
            import webbrowser; webbrowser.open(url); return f"Opening {url}"
        try:
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            return f"Opening {url}"
        except Exception as e: return f"Error: {e}"

    @staticmethod
    def make_call(number):
        if not IS_ANDROID: return f"Would call: {number}"
        try:
            intent = Intent(Intent.ACTION_CALL, Uri.parse(f"tel:{number}"))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            return f"Calling {number}..."
        except Exception as e: return f"Call error: {e}"

    @staticmethod
    def send_whatsapp(number, message=""):
        if not IS_ANDROID: return f"Would WhatsApp: {number}"
        try:
            url = f"https://wa.me/{number}"
            if message: url += f"?text={urllib_quote(message)}"
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.setPackage("com.whatsapp")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            return f"Opening WhatsApp for {number}"
        except Exception as e: return f"WhatsApp error: {e}"

    @staticmethod
    def get_battery():
        if not IS_ANDROID: return "Battery: N/A (desktop)"
        try:
            bm = context.getSystemService("batterymanager")
            level = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            charging = bm.isCharging()
            status = "charging ⚡" if charging else "on battery"
            return f"Battery: {level}% ({status})"
        except Exception as e: return f"Battery error: {e}"

    @staticmethod
    def get_volume():
        if not IS_ANDROID: return "Volume: N/A"
        try:
            am = context.getSystemService("audio")
            cur = am.getStreamVolume(AudioManager.STREAM_MUSIC)
            mx  = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            pct = int(cur / mx * 100)
            return f"Volume: {pct}%"
        except: return "Volume: N/A"

    @staticmethod
    def set_volume(direction):
        if not IS_ANDROID: return f"Would {direction} volume"
        try:
            am = context.getSystemService("audio")
            flag = AudioManager.FLAG_SHOW_UI
            if direction == "up":
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                                      AudioManager.ADJUST_RAISE, flag)
            else:
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                                      AudioManager.ADJUST_LOWER, flag)
            return f"Volume {direction}"
        except Exception as e: return f"Volume error: {e}"

    @staticmethod
    def toggle_wifi(state=None):
        if not IS_ANDROID: return "WiFi toggle: N/A"
        try:
            wm = context.getSystemService("wifi")
            enabled = wm.isWifiEnabled()
            if state == "on" and not enabled:   wm.setWifiEnabled(True);  return "WiFi turned ON"
            if state == "off" and enabled:      wm.setWifiEnabled(False); return "WiFi turned OFF"
            if state is None:
                wm.setWifiEnabled(not enabled)
                return f"WiFi {'OFF' if enabled else 'ON'}"
            return f"WiFi already {'on' if enabled else 'off'}"
        except Exception as e: return f"WiFi error: {e}"

    @staticmethod
    def toggle_bluetooth(state=None):
        if not IS_ANDROID: return "BT toggle: N/A"
        try:
            ba = BluetoothAdapter.getDefaultAdapter()
            if not ba: return "Bluetooth not available"
            enabled = ba.isEnabled()
            if state == "on" and not enabled:   ba.enable();  return "Bluetooth ON"
            if state == "off" and enabled:      ba.disable(); return "Bluetooth OFF"
            if state is None:
                if enabled: ba.disable(); return "Bluetooth OFF"
                else:       ba.enable();  return "Bluetooth ON"
            return f"Bluetooth already {'on' if enabled else 'off'}"
        except Exception as e: return f"Bluetooth error: {e}"

    @staticmethod
    def toggle_flashlight(state=None):
        if not IS_ANDROID: return "Flashlight: N/A"
        try:
            # Android 6+ camera2 flashlight
            cm = context.getSystemService("camera")
            ids = cm.getCameraIdList()
            for cid in ids:
                chars = cm.getCameraCharacteristics(cid)
                from jnius import autoclass
                CameraCharacteristics = autoclass('android.hardware.camera2.CameraCharacteristics')
                has_flash = chars.get(CameraCharacteristics.FLASH_INFO_AVAILABLE)
                if has_flash:
                    turn_on = state == "on" if state else True  # default on if unknown
                    cm.setTorchMode(cid, turn_on)
                    return f"Flashlight {'ON' if turn_on else 'OFF'}"
            return "No flashlight available"
        except Exception as e: return f"Flashlight error: {e}"

    @staticmethod
    def open_settings(page=""):
        if not IS_ANDROID: return "Opening settings..."
        try:
            pages = {
                "wifi":        Settings.ACTION_WIFI_SETTINGS,
                "bluetooth":   Settings.ACTION_BLUETOOTH_SETTINGS,
                "display":     Settings.ACTION_DISPLAY_SETTINGS,
                "sound":       Settings.ACTION_SOUND_SETTINGS,
                "location":    Settings.ACTION_LOCATION_SOURCE_SETTINGS,
                "apps":        Settings.ACTION_APPLICATION_SETTINGS,
                "battery":     Settings.ACTION_BATTERY_SAVER_SETTINGS,
                "storage":     Settings.ACTION_INTERNAL_STORAGE_SETTINGS,
                "":            Settings.ACTION_SETTINGS,
            }
            action = pages.get(page.lower(), Settings.ACTION_SETTINGS)
            intent = Intent(action)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            return f"Opening {page or 'settings'}"
        except Exception as e: return f"Settings error: {e}"

    @staticmethod
    def get_device_info():
        if not IS_ANDROID: return "Device: Desktop (dev mode)"
        try:
            manufacturer = Build.MANUFACTURER
            model        = Build.MODEL
            android_ver  = Build.VERSION.RELEASE
            return f"Device: {manufacturer} {model}\nAndroid: {android_ver}"
        except Exception as e: return f"Info error: {e}"

    @staticmethod
    def search_contacts(name):
        if not IS_ANDROID: return f"Would search contacts for: {name}"
        try:
            cr = context.getContentResolver()
            cursor = cr.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                None,
                f"{ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?",
                [f"%{name}%"],
                None
            )
            results = []
            if cursor:
                while cursor.moveToNext():
                    n_col = cursor.getColumnIndex(
                        ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                    p_col = cursor.getColumnIndex(
                        ContactsContract.CommonDataKinds.Phone.NUMBER)
                    if n_col >= 0 and p_col >= 0:
                        results.append((cursor.getString(n_col), cursor.getString(p_col)))
                cursor.close()
            if results:
                return results[0][0], results[0][1]  # name, number
            return None, None
        except Exception as e: return None, str(e)

    @staticmethod
    def open_camera():
        if not IS_ANDROID: return "Opening camera..."
        try:
            intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent); return "Camera opened"
        except Exception as e: return f"Camera error: {e}"

    @staticmethod
    def open_gallery():
        if not IS_ANDROID: return "Opening gallery..."
        try:
            intent = Intent(Intent.ACTION_VIEW)
            intent.setType("image/*")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent); return "Gallery opened"
        except Exception as e: return f"Gallery error: {e}"


try:
    from urllib.parse import quote as urllib_quote
except ImportError:
    from urllib import quote as urllib_quote


# ─────────────────────────────────────────────────────────────────────────────
#  Brain — command processor (Android-adapted from v6)
# ─────────────────────────────────────────────────────────────────────────────
class Brain:
    # Map app name → Android package
    APP_PACKAGES = {
        "chrome":       "com.android.chrome",
        "youtube":      "com.google.android.youtube",
        "whatsapp":     "com.whatsapp",
        "instagram":    "com.instagram.android",
        "facebook":     "com.facebook.katana",
        "twitter":      "com.twitter.android",
        "x":            "com.twitter.android",
        "spotify":      "com.spotify.music",
        "netflix":      "com.netflix.mediaclient",
        "gmail":        "com.google.android.gm",
        "maps":         "com.google.android.apps.maps",
        "google maps":  "com.google.android.apps.maps",
        "camera":       "com.android.camera2",
        "calculator":   "com.android.calculator2",
        "calendar":     "com.google.android.calendar",
        "contacts":     "com.android.contacts",
        "phone":        "com.android.dialer",
        "messages":     "com.google.android.apps.messaging",
        "settings":     "com.android.settings",
        "photos":       "com.google.android.apps.photos",
        "drive":        "com.google.android.apps.docs",
        "telegram":     "org.telegram.messenger",
        "discord":      "com.discord",
        "amazon":       "com.amazon.mShop.android.shopping",
        "flipkart":     "com.flipkart.android",
        "paytm":        "net.one97.paytm",
        "gpay":         "com.google.android.apps.nbu.paisa.user",
        "phonepe":      "com.phonepe.app",
        "zoom":         "us.zoom.videomeetings",
        "meet":         "com.google.android.apps.meetings",
        "teams":        "com.microsoft.teams",
        "slack":        "com.Slack",
        "clock":        "com.google.android.deskclock",
        "files":        "com.google.android.documentsui",
        "music":        "com.google.android.music",
        "play store":   "com.android.vending",
        "store":        "com.android.vending",
    }

    def __init__(self, helper, tts, config):
        self.helper = helper
        self.tts    = tts
        self.config = config

    def _name(self): return self.config.get("assistant_name", "JINI")
    def _user(self): return self.config.get("user_name", "")

    def _wake_words(self):
        n = self._name().lower()
        return {f"hi {n}", f"hey {n}", f"hello {n}", f"ok {n}", n,
                "hi jini", "hey jini", "jini"}

    def process(self, raw):
        if not raw: return "I didn't catch that."
        raw = raw.strip()
        t   = raw.lower()

        # Strip wake word prefix
        for w in sorted(self._wake_words(), key=len, reverse=True):
            if t.startswith(w + " ") or t.startswith(w + ","):
                raw = raw[len(w):].strip(" ,"); t = raw.lower(); break
            if t == w:
                u = self._user()
                return f"Jo hukum{' ' + u if u else ''}! How can I help?"

        if not raw:
            return f"Jo hukum{' ' + self._user() if self._user() else ''}! How can I help?"

        # ── TIME / DATE ──────────────────────────────────────────────────────
        if re.search(r"\btime\b", t):
            return f"It's {datetime.now().strftime('%I:%M %p')}."
        if re.search(r"\bdate\b|\bday\b|\btoday\b", t):
            return f"Today is {datetime.now().strftime('%A, %d %B %Y')}."

        # ── BATTERY ─────────────────────────────────────────────────────────
        if re.search(r"battery|charge|charging", t):
            return self.helper.get_battery()

        # ── DEVICE INFO ─────────────────────────────────────────────────────
        if re.search(r"device|phone info|about (phone|device)", t):
            return self.helper.get_device_info()

        # ── VOLUME ──────────────────────────────────────────────────────────
        if re.search(r"volume up|louder|increase volume|turn up volume|vol up", t):
            return self.helper.set_volume("up")
        if re.search(r"volume down|quieter|decrease volume|turn down volume|vol down", t):
            return self.helper.set_volume("down")
        if re.search(r"\bvolume\b", t):
            return self.helper.get_volume()

        # ── WIFI ────────────────────────────────────────────────────────────
        if re.search(r"wifi on|turn on wifi|enable wifi", t):
            return self.helper.toggle_wifi("on")
        if re.search(r"wifi off|turn off wifi|disable wifi", t):
            return self.helper.toggle_wifi("off")
        if re.search(r"\bwifi\b", t):
            return self.helper.toggle_wifi()

        # ── BLUETOOTH ───────────────────────────────────────────────────────
        if re.search(r"bluetooth on|turn on bluetooth|enable bluetooth", t):
            return self.helper.toggle_bluetooth("on")
        if re.search(r"bluetooth off|turn off bluetooth|disable bluetooth", t):
            return self.helper.toggle_bluetooth("off")
        if re.search(r"\bbluetooth\b", t):
            return self.helper.toggle_bluetooth()

        # ── FLASHLIGHT ──────────────────────────────────────────────────────
        if re.search(r"flashlight on|torch on|turn on flashlight|turn on torch|flash on", t):
            return self.helper.toggle_flashlight("on")
        if re.search(r"flashlight off|torch off|turn off flashlight|turn off torch|flash off", t):
            return self.helper.toggle_flashlight("off")
        if re.search(r"flashlight|torch", t):
            return self.helper.toggle_flashlight("on")

        # ── CAMERA / GALLERY ────────────────────────────────────────────────
        if re.search(r"open camera|take (a )?photo|selfie", t):
            return self.helper.open_camera()
        if re.search(r"open gallery|view photos|my photos", t):
            return self.helper.open_gallery()

        # ── SETTINGS ────────────────────────────────────────────────────────
        if re.search(r"open wifi settings|wifi settings", t):
            return self.helper.open_settings("wifi")
        if re.search(r"open bluetooth settings|bluetooth settings", t):
            return self.helper.open_settings("bluetooth")
        if re.search(r"open display settings|display settings|brightness settings", t):
            return self.helper.open_settings("display")
        if re.search(r"open sound settings|sound settings", t):
            return self.helper.open_settings("sound")
        if re.search(r"open battery settings|battery settings", t):
            return self.helper.open_settings("battery")
        if re.search(r"open settings|phone settings", t):
            return self.helper.open_settings()

        # ── CALL ────────────────────────────────────────────────────────────
        m = re.search(r"call (.+)", t)
        if m:
            target = m.group(1).strip()
            # Try contacts first
            name, number = self.helper.search_contacts(target)
            if name and number:
                return self.helper.make_call(number.replace(" ", ""))
            # Maybe it's already a number
            digits = re.sub(r"\D", "", target)
            if len(digits) >= 7:
                return self.helper.make_call(digits)
            return f"Couldn't find '{target}' in contacts."

        # ── WHATSAPP ────────────────────────────────────────────────────────
        m = re.search(r"whatsapp (.+?)(?:\s+saying\s+|\s+message\s+|\s+with\s+)?(.+)?", t)
        if m:
            target  = m.group(1).strip()
            message = m.group(2).strip() if m.group(2) else ""
            name, number = self.helper.search_contacts(target)
            if name and number:
                return self.helper.send_whatsapp(number.replace(" ", ""), message)
            digits = re.sub(r"\D", "", target)
            if len(digits) >= 7:
                return self.helper.send_whatsapp(digits, message)
            return f"Couldn't find '{target}' in contacts."

        # ── APP LAUNCH ───────────────────────────────────────────────────────
        m = re.match(r"(?:open|launch|start|run|go to)\s+(.+)", t)
        if m:
            app_name = m.group(1).strip().rstrip(".")
            pkg = self.APP_PACKAGES.get(app_name)
            if pkg:
                return self.helper.open_app(pkg)
            # Try partial match
            for name, package in self.APP_PACKAGES.items():
                if app_name in name or name in app_name:
                    return self.helper.open_app(package)
            return f"App '{app_name}' not found. Try the Play Store."

        # ── YOUTUBE ─────────────────────────────────────────────────────────
        m = re.search(r"(?:play on youtube|play|youtube)\s+(.+)", t)
        if m:
            q = m.group(1).strip()
            url = f"https://www.youtube.com/results?search_query={urllib_quote(q)}"
            return self.helper.open_url(url)

        # ── GOOGLE SEARCH ────────────────────────────────────────────────────
        m = re.search(r"(?:search|google|look up|search for|search on google)\s+(.+)", t)
        if m:
            q = m.group(1).strip()
            return self.helper.open_url(f"https://www.google.com/search?q={urllib_quote(q)}")

        # ── NAVIGATE TO URL ──────────────────────────────────────────────────
        m = re.search(r"(?:go to|visit|open website|navigate to)\s+(https?://\S+|www\.\S+|\S+\.\S+)", t)
        if m:
            url = m.group(1)
            if not url.startswith("http"): url = "https://" + url
            return self.helper.open_url(url)

        # ── WEATHER ─────────────────────────────────────────────────────────
        m = re.search(r"weather\s+(?:in|at|for)?\s*(.+)", t)
        city = m.group(1).strip() if m else ("" if not re.search(r"weather", t) else "")
        if re.search(r"weather", t):
            url = f"https://www.google.com/search?q=weather+{urllib_quote(city)}" if city \
                  else "https://www.google.com/search?q=weather+today"
            self.helper.open_url(url)
            return f"Checking weather{' in ' + city if city else ''}..."

        # ── NEWS ─────────────────────────────────────────────────────────────
        if re.search(r"news|latest news|breaking news", t):
            self.helper.open_url("https://news.google.com")
            return "Opening Google News..."

        # ── MAPS ─────────────────────────────────────────────────────────────
        m = re.search(r"(?:directions to|navigate to|find|map of|get to)\s+(.+)", t)
        if m:
            place = m.group(1).strip()
            url   = f"https://maps.google.com/?q={urllib_quote(place)}"
            return self.helper.open_url(url)

        # ── GREETINGS ────────────────────────────────────────────────────────
        if re.search(r"^(?:hello|hi|hey|sup|howdy|namaste)$", t):
            h = datetime.now().hour
            g = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
            u = self._user()
            return f"Good {g}{(', ' + u) if u else ''}! How can I help?"
        if re.search(r"how are you", t): return "Fully operational and ready to help! 😊"
        if re.search(r"thank|thanks", t): return "You're welcome! Anything else?"
        if re.search(r"who are you|your name|what are you", t):
            return f"I'm {self._name()}, your personal AI assistant! 🤖"
        if re.search(r"what can you do|help|commands", t):
            return (
                "📱 I can help you:\n\n"
                "• Open apps (Chrome, YouTube, WhatsApp...)\n"
                "• Make calls & WhatsApp messages\n"
                "• Control WiFi, Bluetooth, Flashlight\n"
                "• Adjust Volume\n"
                "• Search Google & YouTube\n"
                "• Check Weather & News\n"
                "• Get Directions via Maps\n"
                "• Open Settings pages\n"
                "• Tell Time & Date\n"
                "• Check Battery status\n\n"
                "Just speak or type your command! 🎤"
            )

        # ── JOKES ────────────────────────────────────────────────────────────
        if re.search(r"\bjoke\b", t):
            jokes = [
                "Why don't scientists trust atoms? Because they make up everything! 😄",
                "Why did the smartphone go to school? To improve its reception! 📱",
                "What do you call a fish without eyes? A fsh! 🐟",
                "I told my phone to remind me to exercise. It said 'Okay, reminding you to exercise... someday.' 😂",
                "Why was the math book sad? It had too many problems! 📚",
            ]
            import random
            return random.choice(jokes)

        # ── FALLBACK: Google ──────────────────────────────────────────────────
        self.helper.open_url(f"https://www.google.com/search?q={urllib_quote(raw)}")
        return f"Searching Google for: {raw}"


# ─────────────────────────────────────────────────────────────────────────────
#  UI Widgets
# ─────────────────────────────────────────────────────────────────────────────
class RoundedButton(Button):
    """Styled accent button with rounded corners."""
    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_color", C["accent"])
        kw.setdefault("color", C["white"])
        kw.setdefault("font_size", sp(14))
        kw.setdefault("bold", True)
        super().__init__(**kw)
        self.bind(size=self._redraw, pos=self._redraw)

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.background_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(24)])


class OrbWidget(FloatLayout):
    """Animated pulsing orb — the JINI logo."""
    pulse = NumericProperty(1.0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._anim = None
        self._start_pulse()

    def _start_pulse(self):
        self._anim = Animation(pulse=1.18, duration=0.8, t="in_out_sine") + \
                     Animation(pulse=1.0,  duration=0.8, t="in_out_sine")
        self._anim.repeat = True
        self._anim.start(self)
        self.bind(pulse=self._redraw, size=self._redraw, pos=self._redraw)

    def set_listening(self, is_listening):
        if self._anim: self._anim.cancel(self)
        if is_listening:
            self._anim = Animation(pulse=1.35, duration=0.3, t="in_out_bounce") + \
                         Animation(pulse=1.0,  duration=0.3, t="in_out_bounce")
            self._anim.repeat = True
        else:
            self._anim = Animation(pulse=1.18, duration=0.8, t="in_out_sine") + \
                         Animation(pulse=1.0,  duration=0.8, t="in_out_sine")
            self._anim.repeat = True
        self._anim.start(self)

    def _redraw(self, *_):
        self.canvas.before.clear()
        cx = self.center_x; cy = self.center_y
        r  = min(self.width, self.height) * 0.38 * self.pulse
        with self.canvas.before:
            # Glow ring
            Color(*C["accent"], 0.15)
            Ellipse(pos=(cx - r*1.55, cy - r*1.55), size=(r*3.1, r*3.1))
            # Mid ring
            Color(*C["accent"], 0.25)
            Ellipse(pos=(cx - r*1.25, cy - r*1.25), size=(r*2.5, r*2.5))
            # Core orb
            Color(*C["accent"])
            Ellipse(pos=(cx - r, cy - r), size=(r*2, r*2))
            # Inner highlight
            Color(1, 1, 1, 0.3)
            Ellipse(pos=(cx - r*0.45, cy - r*0.1), size=(r*0.5, r*0.4))


class ChatBubble(BoxLayout):
    """Single chat message bubble."""
    def __init__(self, text, is_user=True, **kw):
        super().__init__(**kw)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.padding     = [dp(8), dp(4)]
        self.spacing     = dp(8)

        color = C["accent"] if is_user else C["bg3"]
        tcolor= C["white"]  if is_user else C["text"]
        halign= "right"     if is_user else "left"

        lbl = Label(
            text=text,
            color=tcolor,
            font_size=sp(13),
            halign=halign,
            valign="middle",
            text_size=(Window.width * 0.65, None),
            size_hint=(None, None),
            padding=[dp(12), dp(10)],
        )
        lbl.bind(texture_size=lambda inst, val: setattr(inst, "size", val))
        lbl.texture_update()

        bubble = FloatLayout(size_hint=(None, None))
        bubble.bind(size=lambda *_: None)

        with bubble.canvas.before:
            Color(*color)
            self._bubble_bg = RoundedRectangle(
                pos=lbl.pos, size=lbl.size,
                radius=[dp(16), dp(16),
                        dp(4) if is_user else dp(16),
                        dp(16) if is_user else dp(4)]
            )

        def _update_bg(*_):
            self._bubble_bg.pos  = lbl.pos
            self._bubble_bg.size = lbl.size
            bubble.size          = lbl.size

        lbl.bind(size=_update_bg, pos=_update_bg)
        lbl.texture_update()
        _update_bg()

        bubble.add_widget(lbl)
        self.height = lbl.height + dp(16)

        spacer = BoxLayout(size_hint_x=1)
        if is_user:
            self.add_widget(spacer)
            self.add_widget(bubble)
        else:
            self.add_widget(bubble)
            self.add_widget(spacer)


# ─────────────────────────────────────────────────────────────────────────────
#  SETUP SCREEN
# ─────────────────────────────────────────────────────────────────────────────
class SetupScreen(Screen):
    def __init__(self, on_done, **kw):
        super().__init__(**kw)
        self.on_done = on_done
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(32), spacing=dp(20))

        with root.canvas.before:
            Color(*C["bg"])
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *_: setattr(self._bg, "pos", root.pos),
                  size=lambda *_: setattr(self._bg, "size", root.size))

        # Orb
        orb = OrbWidget(size_hint=(1, None), height=dp(140))
        root.add_widget(orb)

        # Title
        root.add_widget(Label(
            text="[b]Welcome to JINI[/b]",
            markup=True, font_size=sp(26),
            color=C["text"], size_hint_y=None, height=dp(40)
        ))
        root.add_widget(Label(
            text="Your personal AI assistant",
            font_size=sp(14), color=C["text3"],
            size_hint_y=None, height=dp(24)
        ))

        # Name fields
        self.asst_input = TextInput(
            hint_text="Assistant name (e.g. JINI)",
            text="JINI",
            font_size=sp(15),
            size_hint_y=None, height=dp(52),
            padding=[dp(16), dp(14)],
            multiline=False,
            background_color=C["bg3"],
            foreground_color=C["text"],
            cursor_color=C["accent"],
        )
        self.user_input = TextInput(
            hint_text="Your name",
            font_size=sp(15),
            size_hint_y=None, height=dp(52),
            padding=[dp(16), dp(14)],
            multiline=False,
            background_color=C["bg3"],
            foreground_color=C["text"],
            cursor_color=C["accent"],
        )
        root.add_widget(self.asst_input)
        root.add_widget(self.user_input)

        btn = RoundedButton(text="Let's Go! 🚀", size_hint_y=None, height=dp(54))
        btn.bind(on_press=self._done)
        root.add_widget(btn)

        root.add_widget(BoxLayout())  # spacer
        self.add_widget(root)

    def _done(self, *_):
        asst = self.asst_input.text.strip() or "JINI"
        user = self.user_input.text.strip() or "User"
        self.on_done(asst, user)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APP SCREEN
# ─────────────────────────────────────────────────────────────────────────────
class MainScreen(Screen):
    status_text = StringProperty("Tap the orb or type to start")

    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.app_ref   = app_ref
        self.chat_log  = []
        self._listening = False
        self._build()

    def _build(self):
        root = FloatLayout()

        # Background
        with root.canvas.before:
            Color(*C["bg"])
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *_: setattr(self._bg, "pos", root.pos),
                  size=lambda *_: setattr(self._bg, "size", root.size))

        # ── TOP BAR ──────────────────────────────────────────────────────────
        topbar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None), height=dp(56),
            pos_hint={"top": 1},
            padding=[dp(16), dp(8)],
        )
        with topbar.canvas.before:
            Color(*C["bg2"])
            self._tb_bg = Rectangle(pos=topbar.pos, size=topbar.size)
        topbar.bind(pos=lambda *_: setattr(self._tb_bg, "pos", topbar.pos),
                    size=lambda *_: setattr(self._tb_bg, "size", topbar.size))

        asst = self.app_ref.config.get("assistant_name", "JINI")
        user = self.app_ref.config.get("user_name", "")
        topbar.add_widget(Label(
            text=f"[b]⚡ {asst}[/b]",
            markup=True, font_size=sp(18),
            color=C["accent"], halign="left",
            size_hint_x=1,
        ))

        self.status_lbl = Label(
            text=f"Hi {user}!",
            font_size=sp(11),
            color=C["text3"], halign="right",
            size_hint_x=None, width=dp(100),
        )
        topbar.add_widget(self.status_lbl)
        root.add_widget(topbar)

        # ── CHAT AREA ─────────────────────────────────────────────────────────
        self.scroll = ScrollView(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            do_scroll_x=False,
        )
        self.chat_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
            padding=[dp(8), dp(68), dp(8), dp(190)],
        )
        self.chat_box.bind(minimum_height=self.chat_box.setter("height"))
        self.scroll.add_widget(self.chat_box)
        root.add_widget(self.scroll)

        # ── ORB AREA (bottom centre) ──────────────────────────────────────────
        bottom_panel = BoxLayout(
            orientation="vertical",
            size_hint=(1, None), height=dp(180),
            pos_hint={"x": 0, "y": 0},
            padding=[dp(16), dp(8)],
            spacing=dp(8),
        )
        with bottom_panel.canvas.before:
            Color(*C["bg2"])
            self._bp_bg = RoundedRectangle(pos=bottom_panel.pos,
                                            size=bottom_panel.size,
                                            radius=[dp(28), dp(28), 0, 0])
        bottom_panel.bind(
            pos=lambda *_: setattr(self._bp_bg, "pos", bottom_panel.pos),
            size=lambda *_: setattr(self._bp_bg, "size", bottom_panel.size),
        )

        # Status label
        self.mic_status = Label(
            text=self.status_text,
            font_size=sp(12),
            color=C["text3"],
            size_hint_y=None, height=dp(20),
        )
        bottom_panel.add_widget(self.mic_status)

        # Orb row
        orb_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(80),
                            spacing=dp(16), padding=[dp(24), 0])
        self.orb = OrbWidget(size_hint_x=None, width=dp(80))
        orb_btn = Button(background_normal="", background_color=(0, 0, 0, 0),
                         size_hint_x=None, width=dp(80))
        orb_btn.bind(on_press=self._orb_pressed)

        orb_container = FloatLayout(size_hint_x=None, width=dp(80))
        orb_container.add_widget(self.orb)
        orb_container.add_widget(orb_btn)

        orb_row.add_widget(BoxLayout())  # left spacer
        orb_row.add_widget(orb_container)
        orb_row.add_widget(BoxLayout())  # right spacer
        bottom_panel.add_widget(orb_row)

        # Text input row
        input_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                              height=dp(48), spacing=dp(8))
        self.text_input = TextInput(
            hint_text="Type a command...",
            font_size=sp(14),
            multiline=False,
            size_hint_x=1,
            background_color=C["bg3"],
            foreground_color=C["text"],
            cursor_color=C["accent"],
            padding=[dp(14), dp(12)],
        )
        self.text_input.bind(on_text_validate=self._send_text)

        send_btn = RoundedButton(text="➤", size_hint_x=None, width=dp(52),
                                  font_size=sp(18))
        send_btn.bind(on_press=self._send_text)
        input_row.add_widget(self.text_input)
        input_row.add_widget(send_btn)
        bottom_panel.add_widget(input_row)

        root.add_widget(bottom_panel)
        self.add_widget(root)

    def _orb_pressed(self, *_):
        if self._listening: return
        self.start_listening()

    def start_listening(self):
        self._listening = True
        self.orb.set_listening(True)
        self._update_status("🎤  Listening…", C["red"])
        self.app_ref.voice.start_listening()

    @mainthread
    def on_voice_result(self, text):
        self._listening = False
        self.orb.set_listening(False)
        self._update_status(f'💬 "{text}"', C["text2"])
        self._process(text)

    @mainthread
    def on_voice_error(self, error):
        self._listening = False
        self.orb.set_listening(False)
        self._update_status(f"⚠ {error} — type below", C["yellow"])

    @mainthread
    def on_voice_start(self):
        self._update_status("🎤 Speak now…", C["red"])

    def _send_text(self, *_):
        t = self.text_input.text.strip()
        if not t: return
        self.text_input.text = ""
        self._update_status(f'💬 "{t}"', C["text2"])
        self._process(t)

    def _process(self, text):
        self._add_bubble(text, is_user=True)
        self._update_status("⏳ Processing…", C["yellow"])
        def _bg():
            try:    reply = self.app_ref.brain.process(text)
            except Exception as e: reply = f"Error: {e}"
            self._show_reply(reply)
        threading.Thread(target=_bg, daemon=True).start()

    @mainthread
    def _show_reply(self, reply):
        self._add_bubble(reply, is_user=False)
        self._update_status("Tap orb or type to continue", C["text3"])
        self.app_ref.tts.speak(reply)
        # Scroll to bottom
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def _add_bubble(self, text, is_user):
        bubble = ChatBubble(text=text, is_user=is_user)
        self.chat_box.add_widget(bubble)

    def _update_status(self, text, color):
        self.mic_status.text  = text
        self.mic_status.color = color


# ─────────────────────────────────────────────────────────────────────────────
#  ROOT APP
# ─────────────────────────────────────────────────────────────────────────────
class JINIApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.config_data = load_config()
        self.helper      = AndroidHelper()
        self.tts         = TTSEngine()
        self.brain       = None
        self.voice       = None
        self.main_screen = None

    def build(self):
        Window.clearcolor = get_color_from_hex("#F0F4FF")
        self.sm = ScreenManager(transition=SlideTransition())

        if not self.config_data.get("assistant_name") or not self.config_data.get("user_name"):
            setup = SetupScreen(on_done=self._finish_setup, name="setup")
            self.sm.add_widget(setup)
        else:
            self._launch_main()

        return self.sm

    def on_start(self):
        if IS_ANDROID:
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.READ_CONTACTS,
                Permission.CALL_PHONE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.ACCESS_FINE_LOCATION,
                Permission.CAMERA,
                Permission.VIBRATE,
            ])

    def _finish_setup(self, asst, user):
        self.config_data["assistant_name"] = asst
        self.config_data["user_name"]      = user
        save_config(self.config_data)
        self._launch_main()

    def _launch_main(self):
        self.brain = Brain(self.helper, self.tts, self.config_data)
        self.voice = VoiceRecogniser(
            on_result=lambda t: self.main_screen.on_voice_result(t) if self.main_screen else None,
            on_error =lambda e: self.main_screen.on_voice_error(e)  if self.main_screen else None,
            on_start =lambda:   self.main_screen.on_voice_start()   if self.main_screen else None,
        )
        self.main_screen = MainScreen(app_ref=self, name="main")
        if "setup" in [s.name for s in self.sm.screens]:
            self.sm.current = "setup"
            self.sm.add_widget(self.main_screen)
            self.sm.current = "main"
        else:
            self.sm.add_widget(self.main_screen)
            self.sm.current = "main"

        # Welcome message
        asst = self.config_data.get("assistant_name", "JINI")
        user = self.config_data.get("user_name", "")
        greeting = f"Hello{(' ' + user) if user else ''}! {asst} is ready. How can I help?"
        Clock.schedule_once(lambda dt: self._welcome(greeting), 0.8)

    def _welcome(self, text):
        if self.main_screen:
            self.main_screen._add_bubble(text, is_user=False)
            self.tts.speak(text)

    def on_pause(self):
        return True  # keep app alive when minimised

    def on_resume(self):
        pass


if __name__ == "__main__":
    JINIApp().run()
