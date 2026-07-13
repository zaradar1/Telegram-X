package com.telegramx.manager

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import kotlin.concurrent.thread

class AccountFragment : Fragment(R.layout.fragment_account) {

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val phoneText = view.findViewById<TextView>(R.id.accountPhone)
        val logoutButton = view.findViewById<Button>(R.id.logoutButton)

        val phone = (activity as? MainActivity)?.activePhone
        phoneText.text = phone ?: getString(R.string.error_not_logged_in)

        logoutButton.setOnClickListener {
            val main = activity as? MainActivity ?: return@setOnClickListener
            val p = main.activePhone
            logoutButton.isEnabled = false
            thread {
                if (p != null) PyBridge.logout(p)
                activity?.runOnUiThread {
                    main.activePhone = null
                    main.onLoggedOut()
                }
            }
        }
    }
}
