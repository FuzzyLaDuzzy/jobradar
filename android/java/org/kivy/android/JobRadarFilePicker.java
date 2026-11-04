package org.kivy.android;  // the bootstrap's package: mWebView is protected

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.util.Log;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;

/**
 * The app's window (python-for-android's webview bootstrap) has no file chooser of its own: without
 * this, "choose your CV" in Profile does nothing. It opens Android's picker for an input type="file"
 * and hands the chosen file back to the page, which reads it as on a computer.
 */
public class JobRadarFilePicker extends WebChromeClient implements PythonActivity.ActivityResultListener {
    private static final int REQUEST = 7301;
    private ValueCallback<Uri[]> pending;

    /** Called by android/main.py once Python runs: the window exists by then. */
    public static void install() {
        PythonActivity.mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                JobRadarFilePicker picker = new JobRadarFilePicker();
                PythonActivity.mActivity.registerActivityResultListener(picker);
                PythonActivity.mWebView.setWebChromeClient(picker);
                Log.i("JobRadar", "file picker ready");
            }
        });
    }

    @Override
    public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
        if (pending != null) {
            pending.onReceiveValue(null);  // an earlier one never came back
        }
        pending = callback;
        try {
            PythonActivity.mActivity.startActivityForResult(params.createIntent(), REQUEST);  // accept=".pdf"
        } catch (ActivityNotFoundException e) {
            pending = null;
            return false;
        }
        return true;
    }

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != REQUEST || pending == null) {
            return;
        }
        pending.onReceiveValue(FileChooserParams.parseResult(resultCode, data));  // null when cancelled
        pending = null;
    }
}
