package br.com.chatfacil.placeholder;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.TextView;

/** Minimal native shell; the workspace supplied no application source to port. */
public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        TextView message = new TextView(this);
        message.setText("Chat Fácil\n\nProjeto Android inicial. Adicione o código do app para continuar.");
        message.setGravity(Gravity.CENTER);
        message.setPadding(32, 32, 32, 32);
        setContentView(message);
    }
}
