#!/data/data/com.termux/files/usr/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT=/storage/emulated/0/Download/Chat-Facil.apk
BUILD="$ROOT/.android-build"
ANDROID_JAR="${ANDROID_JAR:-$PREFIX/share/java/android.jar}"
FRAMEWORK_RES="${FRAMEWORK_RES:-/system/framework/framework-res.apk}"

rm -rf "$BUILD"
mkdir -p "$BUILD/classes"
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -d "$BUILD/classes" \
  "$ROOT/src/br/com/chatfacil/placeholder/MainActivity.java"
dx --dex --output="$BUILD/classes.dex" "$BUILD/classes"
aapt package -f -M "$ROOT/AndroidManifest.xml" -I "$ANDROID_JAR" \
  -I "$FRAMEWORK_RES" -F "$BUILD/unsigned.apk"
mkdir -p "$BUILD/apk"
cd "$BUILD/apk"
unzip -q "$BUILD/unsigned.apk"
cp "$BUILD/classes.dex" .
zip -q -r "$BUILD/unsigned-with-dex.apk" .
keytool -genkeypair -keystore "$BUILD/debug.keystore" -storepass android \
  -keypass android -alias androiddebugkey -dname "CN=Android Debug,O=Android,C=US" \
  -keyalg RSA -keysize 2048 -validity 10000 >/dev/null 2>&1
zipalign -f 4 "$BUILD/unsigned-with-dex.apk" "$BUILD/aligned.apk"
apksigner sign --ks "$BUILD/debug.keystore" --ks-pass pass:android \
  --key-pass pass:android --out "$OUT" "$BUILD/aligned.apk"
apksigner verify --verbose "$OUT"
ls -lh "$OUT"
