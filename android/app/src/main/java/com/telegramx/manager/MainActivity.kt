package com.telegramx.manager

import android.content.Context
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.bottomnavigation.BottomNavigationView
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var bottomNav: BottomNavigationView

    val prefs by lazy { getSharedPreferences("telegram_manager", Context.MODE_PRIVATE) }

    var activePhone: String?
        get() = prefs.getString(KEY_ACTIVE_PHONE, null)
        set(value) = prefs.edit().putString(KEY_ACTIVE_PHONE, value).apply()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        PyBridge.init(this)

        bottomNav = findViewById(R.id.bottomNav)
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_chats -> showFragment(ChatsFragment())
                R.id.nav_jobs -> showFragment(JobsFragment())
                R.id.nav_account -> showFragment(AccountFragment())
            }
            true
        }

        if (savedInstanceState == null) {
            bottomNav.visibility = android.view.View.GONE
            val phone = activePhone
            if (phone != null) {
                thread {
                    val loggedIn = PyBridge.isLoggedIn(phone)
                    runOnUiThread {
                        if (loggedIn) {
                            bottomNav.visibility = android.view.View.VISIBLE
                            bottomNav.selectedItemId = R.id.nav_chats
                        } else {
                            showFragment(LoginFragment())
                        }
                    }
                }
            } else {
                showFragment(LoginFragment())
            }
        }
    }

    fun onLoginSuccess() {
        bottomNav.visibility = android.view.View.VISIBLE
        bottomNav.selectedItemId = R.id.nav_chats
    }

    fun onLoggedOut() {
        bottomNav.visibility = android.view.View.GONE
        showFragment(LoginFragment())
    }

    private fun showFragment(fragment: Fragment) {
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragmentContainer, fragment)
            .commit()
    }

    companion object {
        private const val KEY_ACTIVE_PHONE = "active_phone"
    }
}
