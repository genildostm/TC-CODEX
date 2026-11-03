package com.chatfacil;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.provider.OpenableColumns;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.content.SharedPreferences;
import android.text.InputType;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private WebView webView;
    private SharedPreferences prefs;
    private static final String PREFS = "chat_facil_private";
    private static final String TOKEN = "bridge_pair_code";
    private static final String WORKSPACE = "workspace_path";
    private static final String OUTPUT = "output_path";
    private static final String BRIDGE = "http://127.0.0.1:8766";
    private static final int PICK_ATTACHMENT = 82;
    private String uploadSessionId = "";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(0xfff7f7f5);
        getWindow().setNavigationBarColor(0xfff7f7f5);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        webView = new WebView(this);
        webView.setBackgroundColor(0xfff7f7f5);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setAllowFileAccess(true);
        webView.getSettings().setAllowContentAccess(false);
        webView.addJavascriptInterface(new ChatBridge(), "AndroidChat");
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !"file".equals(request.getUrl().getScheme());
            }
        });
        setContentView(webView);
        webView.loadUrl("file:///android_asset/index.html");
        webView.postDelayed(new Runnable() { public void run() { checkConnection(); if (prefs.getString(TOKEN, "").isEmpty()) showBridgeDialog(); } }, 600);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_ATTACHMENT) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.attachmentFailed(\"Anexo não selecionado\")", null); return; }
        final Uri uri = data.getData();
        final String sid = uploadSessionId;
        updateStatus(true, "Preparando anexo…");
        new Thread(new Runnable() { public void run() { uploadAttachment(uri, sid); }}).start();
    }

    private String displayName(Uri uri) {
        Cursor cursor = null;
        try {
            cursor = getContentResolver().query(uri, null, null, null, null);
            if (cursor != null && cursor.moveToFirst()) {
                int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (column >= 0) return cursor.getString(column);
            }
        } catch (Exception ignored) {} finally { if (cursor != null) cursor.close(); }
        String name = uri.getLastPathSegment();
        return name == null ? "anexo" : name;
    }

    private void uploadAttachment(Uri uri, String sessionId) {
        File staged = null; HttpURLConnection conn = null;
        try {
            String name = displayName(uri);
            String suffix = name.contains(".") ? name.substring(name.lastIndexOf('.')).toLowerCase() : "";
            if (!(suffix.equals(".apk") || suffix.equals(".png") || suffix.equals(".jpg") || suffix.equals(".jpeg") || suffix.equals(".webp") || suffix.equals(".gif"))) throw new Exception("Escolha um APK ou imagem PNG, JPG, WEBP ou GIF.");
            staged = File.createTempFile("chat-facil-", suffix, getCacheDir());
            long size = 0; byte[] buffer = new byte[65536];
            try (InputStream input = getContentResolver().openInputStream(uri); FileOutputStream output = new FileOutputStream(staged)) {
                if (input == null) throw new Exception("Não consegui ler o arquivo selecionado.");
                int n; while ((n=input.read(buffer))!=-1) { size += n; if (size > 250L*1024*1024) throw new Exception("O arquivo ultrapassa o limite de 250 MB."); output.write(buffer,0,n); }
            }
            String query = "?workspace=" + java.net.URLEncoder.encode(prefs.getString(WORKSPACE, "~/TC-Codex/workspace"), "UTF-8") + "&session_id=" + java.net.URLEncoder.encode(sessionId, "UTF-8") + "&name=" + java.net.URLEncoder.encode(name, "UTF-8");
            conn = (HttpURLConnection)new URL(BRIDGE + "/api/upload" + query).openConnection();
            conn.setRequestMethod("PUT"); conn.setConnectTimeout(15000); conn.setReadTimeout(600000); conn.setDoOutput(true); conn.setFixedLengthStreamingMode(staged.length());
            conn.setRequestProperty("Authorization", "Bearer " + prefs.getString(TOKEN, ""));
            conn.setRequestProperty("Content-Type", getContentResolver().getType(uri) == null ? "application/octet-stream" : getContentResolver().getType(uri));
            try (InputStream input = new java.io.FileInputStream(staged); OutputStream output = conn.getOutputStream()) { int n; while ((n=input.read(buffer))!=-1) output.write(buffer,0,n); }
            int status = conn.getResponseCode(); InputStream responseStream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            ByteArrayOutputStream responseBytes = new ByteArrayOutputStream(); int n; while ((n=responseStream.read(buffer))!=-1) responseBytes.write(buffer,0,n);
            final String json = new String(responseBytes.toByteArray(), StandardCharsets.UTF_8);
            runOnUiThread(new Runnable() { public void run() { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.attachmentUploaded(" + JSONObject.quote(json) + ")", null); }});
        } catch (Exception e) {
            final String error = e.getMessage() == null ? "Falha ao enviar o anexo." : e.getMessage();
            runOnUiThread(new Runnable() { public void run() { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.attachmentFailed(" + JSONObject.quote(error) + ")", null); }});
        } finally { if (conn != null) conn.disconnect(); if (staged != null) staged.delete(); }
    }

    @Override protected void onResume() {
        super.onResume();
        if (webView != null) webView.postDelayed(new Runnable() { public void run() {
            webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.refreshApps()", null);
            checkConnection();
        } }, 250);
    }

    private EditText field(String value, String hint, boolean secret) {
        EditText input = new EditText(this);
        input.setSingleLine(true); input.setText(value); input.setHint(hint);
        input.setInputType(secret ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        return input;
    }

    private void showBridgeDialog() {
        final EditText code = field(prefs.getString(TOKEN, ""), "Código mostrado no Termux", true);
        final EditText path = field(prefs.getString(WORKSPACE, "~/TC-Codex/workspace"), "~/TC-Codex/workspace", false);
        final EditText outputPath = field(prefs.getString(OUTPUT, "~/storage/downloads"), "~/storage/downloads", false);
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(48, 8, 48, 0);
        TextView codeLabel = new TextView(this); codeLabel.setText("Código de pareamento"); box.addView(codeLabel); box.addView(code);
        TextView pathLabel = new TextView(this); pathLabel.setText("Pasta do projeto (onde o Codex pode trabalhar)"); pathLabel.setPadding(0, 14, 0, 0); box.addView(pathLabel); box.addView(path);
        TextView outputLabel = new TextView(this); outputLabel.setText("Pasta para salvar APKs, relatórios e arquivos finais"); outputLabel.setPadding(0, 14, 0, 0); box.addView(outputLabel); box.addView(outputPath);
        ScrollView scroll = new ScrollView(this); scroll.addView(box);
        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("Conectar ao Termux")
            .setMessage("O Codex usará sua sessão autenticada. Downloads é a pasta de saída padrão.")
            .setView(scroll)
            .setPositiveButton("Conectar", null)
            .setNegativeButton("Cancelar", null)
            .setNeutralButton("Desconectar", null)
            .create();
        dialog.setOnShowListener(new android.content.DialogInterface.OnShowListener() { public void onShow(android.content.DialogInterface d) {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(new View.OnClickListener() { public void onClick(View v) {
                String pairing = code.getText().toString().trim(), workspace = path.getText().toString().trim(), output = outputPath.getText().toString().trim();
                if (pairing.length() < 20 || workspace.isEmpty() || output.isEmpty()) { Toast.makeText(MainActivity.this, "Confira o código e as pastas.", Toast.LENGTH_SHORT).show(); return; }
                prefs.edit().putString(TOKEN, pairing).putString(WORKSPACE, workspace).putString(OUTPUT, output).apply();
                ((InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(path.getWindowToken(), 0);
                dialog.dismiss(); checkConnection();
            }});
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(new View.OnClickListener() { public void onClick(View v) { prefs.edit().remove(TOKEN).apply(); dialog.dismiss(); updateStatus(false, "Desconectado"); }});
        }});
        dialog.show();
    }

    private void updateStatus(final boolean connected, final String message) {
        if (webView != null) webView.post(new Runnable() { public void run() {
            webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.setStatus(" + (connected ? "true" : "false") + "," + JSONObject.quote(message) + ")", null);
        }});
    }

    private void checkConnection() {
        final String token = prefs.getString(TOKEN, "");
        if (token.isEmpty()) { updateStatus(false, "Conecte ao Termux"); return; }
        new Thread(new Runnable() { public void run() {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection)new URL(BRIDGE + "/api/status").openConnection();
                conn.setConnectTimeout(4000); conn.setReadTimeout(5000); conn.setRequestProperty("Authorization", "Bearer " + token);
                InputStream in = conn.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] b = new byte[1024]; int n;
                while ((n=in.read(b))!=-1) out.write(b,0,n);
                JSONObject data = new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
                updateStatus(data.optBoolean("connected"), data.optString("message", "Conectado ao Termux"));
            } catch (Exception e) { updateStatus(false, "Inicie bridge.py no Termux"); }
            finally { if (conn != null) conn.disconnect(); }
        }}).start();
    }

    private class ChatBridge {
        @JavascriptInterface public void configureBridge() { runOnUiThread(new Runnable() { public void run() { showBridgeDialog(); }}); }
        @JavascriptInterface public boolean hasPairing() { return !prefs.getString(TOKEN, "").isEmpty(); }
        @JavascriptInterface public void setWorkspacePath(String path) { prefs.edit().putString(WORKSPACE, path).apply(); Toast.makeText(MainActivity.this, "Pasta do projeto atualizada", Toast.LENGTH_SHORT).show(); }
        @JavascriptInterface public void setOutputPath(String path) { prefs.edit().putString(OUTPUT, path).apply(); Toast.makeText(MainActivity.this, "Pasta de saída atualizada", Toast.LENGTH_SHORT).show(); }
        @JavascriptInterface public void pickAttachment(final String sessionId) { runOnUiThread(new Runnable() { public void run() {
            uploadSessionId = sessionId;
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT); intent.addCategory(Intent.CATEGORY_OPENABLE); intent.setType("*/*");
            intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"image/png", "image/jpeg", "image/webp", "image/gif", "application/vnd.android.package-archive"});
            startActivityForResult(intent, PICK_ATTACHMENT);
        }}); }
        @JavascriptInterface public String installedApps() {
            org.json.JSONArray apps = new org.json.JSONArray();
            try {
                PackageManager manager = getPackageManager();
                for (ApplicationInfo info : manager.getInstalledApplications(0)) {
                    if ((info.flags & ApplicationInfo.FLAG_SYSTEM) != 0 || info.packageName.equals(getPackageName())) continue;
                    JSONObject app = new JSONObject();
                    app.put("name", manager.getApplicationLabel(info).toString()); app.put("package", info.packageName);
                    apps.put(app);
                }
            } catch (Exception ignored) {}
            return apps.toString();
        }
        @JavascriptInterface public void uninstallApp(final String packageName) {
            runOnUiThread(new Runnable() { public void run() {
                try {
                    ApplicationInfo info = getPackageManager().getApplicationInfo(packageName, 0);
                    if ((info.flags & ApplicationInfo.FLAG_SYSTEM) != 0 || packageName.equals(getPackageName())) throw new Exception("Este app do sistema não pode ser removido por aqui.");
                    startActivity(new Intent(Intent.ACTION_DELETE, Uri.parse("package:" + packageName)));
                } catch (Exception e) { Toast.makeText(MainActivity.this, e.getMessage() == null ? "Não foi possível abrir o desinstalador." : e.getMessage(), Toast.LENGTH_LONG).show(); }
            }});
        }
        @JavascriptInterface public void browseFiles(final String path, final String callbackId) { new Thread(new Runnable() { public void run() { fileRequest("GET", path, null, callbackId); }}).start(); }
        @JavascriptInterface public void discardAttachment(final String uploadId) { new Thread(new Runnable() { public void run() {
            HttpURLConnection conn = null; try { conn = (HttpURLConnection)new URL(BRIDGE + "/api/upload/" + uploadId).openConnection(); conn.setRequestMethod("DELETE"); conn.setConnectTimeout(5000); conn.setReadTimeout(5000); conn.setRequestProperty("Authorization", "Bearer " + prefs.getString(TOKEN, "")); conn.getResponseCode(); } catch (Exception ignored) {} finally { if (conn != null) conn.disconnect(); }
        }}).start(); }
        @JavascriptInterface public void deleteFile(final String path, final String confirmedName, final String callbackId) { new Thread(new Runnable() { public void run() {
            JSONObject body = new JSONObject(); try { body.put("path", path); body.put("confirmed_name", confirmedName); } catch (Exception ignored) {}
            fileRequest("POST", path, body.toString(), callbackId);
        }}).start(); }
        private void fileRequest(String method, String path, String body, String callbackId) {
            HttpURLConnection conn = null; JSONObject result;
            try {
                String token = prefs.getString(TOKEN, ""); if (token.isEmpty()) throw new Exception("Conecte o app ao Termux primeiro.");
                String url = BRIDGE + ("GET".equals(method) ? "/api/files?path=" + Uri.encode(path) : "/api/files/delete");
                conn = (HttpURLConnection)new URL(url).openConnection(); conn.setRequestMethod(method); conn.setConnectTimeout(5000); conn.setReadTimeout(15000);
                conn.setRequestProperty("Authorization", "Bearer " + token);
                if (body != null) { conn.setDoOutput(true); conn.setRequestProperty("Content-Type", "application/json; charset=utf-8"); try (OutputStream out = conn.getOutputStream()) { out.write(body.getBytes(StandardCharsets.UTF_8)); } }
                int code = conn.getResponseCode(); InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int n; while ((n=in.read(buffer))!=-1) out.write(buffer,0,n);
                result = new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8)); if (code >= 400 && !result.has("error")) result.put("error", "Operação recusada pelo serviço local.");
            } catch (Exception e) { result = new JSONObject(); try { result.put("error", e.getMessage() == null ? "Falha ao acessar os arquivos do Termux." : e.getMessage()); } catch (Exception ignored) {} }
            finally { if (conn != null) conn.disconnect(); }
            final String json = result.toString(); runOnUiThread(new Runnable() { public void run() { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.fileResult(" + JSONObject.quote(callbackId) + "," + JSONObject.quote(json) + ")", null); }});
        }
        @JavascriptInterface public void send(String raw, String callbackId) { new Thread(new Runnable() { public void run() { sendToBridge(raw, callbackId); }}).start(); }
        private void sendToBridge(String raw, String callbackId) {
            JSONObject result = new JSONObject(); HttpURLConnection conn = null;
            try {
                String token = prefs.getString(TOKEN, "");
                if (token.isEmpty()) throw new Exception("Conecte o app ao Termux pelo menu de configurações.");
                JSONObject request = new JSONObject(raw);
                request.put("workspace", prefs.getString(WORKSPACE, "~/TC-Codex/workspace"));
                request.put("output_dir", prefs.getString(OUTPUT, "~/storage/downloads"));
                conn = (HttpURLConnection)new URL(BRIDGE + "/api/chat").openConnection();
                conn.setRequestMethod("POST"); conn.setConnectTimeout(10000); conn.setReadTimeout(1200000); conn.setDoOutput(true);
                conn.setRequestProperty("Authorization", "Bearer " + token); conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                byte[] bytes = request.toString().getBytes(StandardCharsets.UTF_8);
                try (OutputStream out = conn.getOutputStream()) { out.write(bytes); }
                int status = conn.getResponseCode(); InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int count;
                while ((count=stream.read(buffer))!=-1) out.write(buffer,0,count);
                JSONObject response = new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
                if (status >= 400) result.put("error", response.optString("error", "Falha no serviço local."));
                else result.put("answer", response.optString("answer", "O Codex não retornou uma resposta."));
            } catch (Exception e) { try { result.put("error", e.getMessage() == null ? "Não consegui conectar ao serviço do Termux." : e.getMessage()); } catch (Exception ignored) {} }
            finally { if (conn != null) conn.disconnect(); }
            final String json = result.toString();
            runOnUiThread(new Runnable() { public void run() { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.receive(" + JSONObject.quote(callbackId) + "," + JSONObject.quote(json) + ")", null); }});
        }
    }

    @Override public void onBackPressed() { if (webView != null) { webView.evaluateJavascript("window.ChatFacil && window.ChatFacil.handleBack()", null); return; } super.onBackPressed(); }
}
