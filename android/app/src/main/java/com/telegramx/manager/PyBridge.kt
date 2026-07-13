package com.telegramx.manager

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

fun PyObject.getStr(key: String): String? {
    val v = this.callAttr("get", key) ?: return null
    return if (v.toString() == "None") null else v.toString()
}

fun PyObject.getBool(key: String, default: Boolean = false): Boolean {
    val v = this.callAttr("get", key) ?: return default
    return if (v.toString() == "None") default else v.toBoolean()
}

fun PyObject.getInt(key: String, default: Int = 0): Int {
    val v = this.callAttr("get", key) ?: return default
    return if (v.toString() == "None") default else v.toInt()
}

fun PyObject.getLong(key: String, default: Long = 0L): Long {
    val v = this.callAttr("get", key) ?: return default
    return if (v.toString() == "None") default else v.toLong()
}

object PyBridge {
    private lateinit var api: PyObject

    fun init(context: Context) {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context.applicationContext))
        }
        api = Python.getInstance().getModule("api")
    }

    fun sendCode(phone: String, apiId: Int, apiHash: String): PyObject =
        api.callAttr("send_code", phone, apiId, apiHash)

    fun verifyCode(phone: String, code: String): PyObject =
        api.callAttr("verify_code", phone, code)

    fun verify2fa(phone: String, password: String): PyObject =
        api.callAttr("verify_2fa", phone, password)

    fun isLoggedIn(phone: String): Boolean =
        api.callAttr("is_logged_in", phone).toBoolean()

    fun logout(phone: String) {
        api.callAttr("logout", phone)
    }

    fun listAccounts(): List<PyObject> =
        api.callAttr("list_accounts").asList()

    fun listChats(phone: String): List<PyObject> =
        api.callAttr("list_chats", phone).asList()

    fun startBulkDownload(phone: String, chatId: Long, limit: Int): PyObject =
        api.callAttr("start_bulk_download", phone, chatId, limit)

    fun listJobs(): List<PyObject> =
        api.callAttr("list_jobs").asList()

    fun pauseJob(jobId: String) {
        api.callAttr("pause_job", jobId)
    }

    fun resumeJob(jobId: String) {
        api.callAttr("resume_job", jobId)
    }

    fun stopJob(jobId: String) {
        api.callAttr("stop_job", jobId)
    }
}
