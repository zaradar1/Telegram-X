package com.telegramx.manager

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import kotlin.concurrent.thread

class LoginFragment : Fragment(R.layout.fragment_login) {

    private enum class Step { CREDENTIALS, CODE, TWO_FA }

    private var step = Step.CREDENTIALS
    private var phone: String = ""

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        render(view)
    }

    private fun render(view: View) {
        val title = view.findViewById<TextView>(R.id.loginTitle)
        val phoneField = view.findViewById<EditText>(R.id.phoneField)
        val apiIdField = view.findViewById<EditText>(R.id.apiIdField)
        val apiHashField = view.findViewById<EditText>(R.id.apiHashField)
        val codeField = view.findViewById<EditText>(R.id.codeField)
        val passwordField = view.findViewById<EditText>(R.id.passwordField)
        val actionButton = view.findViewById<Button>(R.id.actionButton)
        val statusText = view.findViewById<TextView>(R.id.statusText)

        phoneField.visibility = if (step == Step.CREDENTIALS) View.VISIBLE else View.GONE
        apiIdField.visibility = if (step == Step.CREDENTIALS) View.VISIBLE else View.GONE
        apiHashField.visibility = if (step == Step.CREDENTIALS) View.VISIBLE else View.GONE
        codeField.visibility = if (step == Step.CODE) View.VISIBLE else View.GONE
        passwordField.visibility = if (step == Step.TWO_FA) View.VISIBLE else View.GONE

        when (step) {
            Step.CREDENTIALS -> {
                title.text = getString(R.string.login_title)
                actionButton.text = getString(R.string.action_send_code)
            }
            Step.CODE -> {
                title.text = getString(R.string.verify_code_title, phone)
                actionButton.text = getString(R.string.action_verify)
            }
            Step.TWO_FA -> {
                title.text = getString(R.string.two_fa_title)
                actionButton.text = getString(R.string.action_verify)
            }
        }

        actionButton.setOnClickListener {
            actionButton.isEnabled = false
            statusText.text = ""
            when (step) {
                Step.CREDENTIALS -> {
                    val p = phoneField.text.toString().trim()
                    val idText = apiIdField.text.toString().trim()
                    val hash = apiHashField.text.toString().trim()
                    if (p.isEmpty() || idText.isEmpty() || hash.isEmpty()) {
                        statusText.text = getString(R.string.error_fill_all)
                        actionButton.isEnabled = true
                        return@setOnClickListener
                    }
                    val apiId = idText.toIntOrNull()
                    if (apiId == null) {
                        statusText.text = getString(R.string.error_api_id_number)
                        actionButton.isEnabled = true
                        return@setOnClickListener
                    }
                    phone = p
                    thread {
                        val result = PyBridge.sendCode(p, apiId, hash)
                        activity?.runOnUiThread {
                            actionButton.isEnabled = true
                            if (result.getBool("ok")) {
                                step = Step.CODE
                                render(view)
                            } else {
                                statusText.text = result.getStr("error") ?: getString(R.string.error_unknown)
                            }
                        }
                    }
                }
                Step.CODE -> {
                    val code = codeField.text.toString().trim()
                    if (code.isEmpty()) {
                        statusText.text = getString(R.string.error_enter_code)
                        actionButton.isEnabled = true
                        return@setOnClickListener
                    }
                    thread {
                        val result = PyBridge.verifyCode(phone, code)
                        activity?.runOnUiThread {
                            actionButton.isEnabled = true
                            when {
                                result.getBool("needs_2fa") -> {
                                    step = Step.TWO_FA
                                    render(view)
                                }
                                result.getBool("ok") -> onLoggedIn()
                                else -> statusText.text = result.getStr("error") ?: getString(R.string.error_unknown)
                            }
                        }
                    }
                }
                Step.TWO_FA -> {
                    val password = passwordField.text.toString()
                    if (password.isEmpty()) {
                        statusText.text = getString(R.string.error_enter_password)
                        actionButton.isEnabled = true
                        return@setOnClickListener
                    }
                    thread {
                        val result = PyBridge.verify2fa(phone, password)
                        activity?.runOnUiThread {
                            actionButton.isEnabled = true
                            if (result.getBool("ok")) {
                                onLoggedIn()
                            } else {
                                statusText.text = result.getStr("error") ?: getString(R.string.error_unknown)
                            }
                        }
                    }
                }
            }
        }
    }

    private fun onLoggedIn() {
        val main = activity as? MainActivity ?: return
        main.activePhone = phone
        main.onLoginSuccess()
    }
}
