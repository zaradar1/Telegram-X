package com.telegramx.manager

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Context
import android.os.Bundle
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.ProgressBar
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var emptyState: android.view.View

    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        setSupportActionBar(findViewById<Toolbar>(R.id.toolbar))

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        progressBar = findViewById(R.id.progressBar)
        emptyState = findViewById(R.id.emptyState)

        findViewById<android.widget.Button>(R.id.setUrlButton).setOnClickListener {
            promptForUrl()
        }

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.databaseEnabled = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                progressBar.visibility = android.view.View.GONE
            }
        }
        webView.webChromeClient = object : android.webkit.WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.visibility = if (newProgress < 100) android.view.View.VISIBLE else android.view.View.GONE
                progressBar.progress = newProgress
            }
        }

        swipeRefresh.setOnRefreshListener { webView.reload() }

        loadSavedUrlOrPrompt()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_reload -> {
                webView.reload()
                true
            }
            R.id.action_change_url -> {
                promptForUrl()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    private fun loadSavedUrlOrPrompt() {
        val savedUrl = prefs.getString(KEY_URL, null)
        if (savedUrl.isNullOrBlank()) {
            showEmptyState(true)
            promptForUrl()
        } else {
            showEmptyState(false)
            webView.loadUrl(savedUrl)
        }
    }

    private fun showEmptyState(show: Boolean) {
        emptyState.visibility = if (show) android.view.View.VISIBLE else android.view.View.GONE
        webView.visibility = if (show) android.view.View.GONE else android.view.View.VISIBLE
    }

    private fun promptForUrl() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            hint = getString(R.string.dialog_url_hint)
            setText(prefs.getString(KEY_URL, ""))
        }

        AlertDialog.Builder(this)
            .setTitle(R.string.dialog_url_title)
            .setMessage(R.string.dialog_url_message)
            .setView(input)
            .setPositiveButton(R.string.action_save) { _, _ ->
                val entered = input.text.toString().trim()
                if (entered.isNotEmpty()) {
                    val url = if (!entered.startsWith("http://") && !entered.startsWith("https://")) {
                        "https://$entered"
                    } else {
                        entered
                    }
                    prefs.edit().putString(KEY_URL, url).apply()
                    showEmptyState(false)
                    webView.loadUrl(url)
                }
            }
            .setNegativeButton(R.string.action_cancel, null)
            .show()
    }

    companion object {
        private const val PREFS_NAME = "telegram_manager_prefs"
        private const val KEY_URL = "server_url"
    }
}
