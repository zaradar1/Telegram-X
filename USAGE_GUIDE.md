# 📱 Complete Usage Guide - Telegram Account Manager

## 🚀 Quick Start

### Step 1: Install & Run
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app opens at: **http://localhost:8501**

---

## 📖 Full User Interface Guide

The app has **3 main tabs** with different features:

---

## 🔐 Tab 1: LOGIN (First Time)

### Purpose
Login to your Telegram account using API credentials and phone number.

### Required Inputs

#### **Step 1️⃣ - API Credentials**

1. **API ID** (Number input field)
   - What: Your Telegram app ID
   - Where to get: https://my.telegram.org/
   - Example: `12345678`
   - How: 
     - Visit my.telegram.org
     - Login with phone number
     - Go to "API development tools"
     - Click "Create new application"
     - Copy the "App api_id"

2. **API Hash** (Password field - hidden)
   - What: Your Telegram app hash
   - Where to get: https://my.telegram.org/
   - Example: `a1b2c3d4e5f6g7h8...`
   - How: 
     - Same place as API ID
     - Copy the "App api_hash" (long string)

#### **Step 2️⃣ - Phone Number**

3. **Phone Number** (Text input)
   - Format: **Must include country code**
   - Example: `+1234567890` (USA)
   - Examples by country:
     - 🇮🇳 India: `+919876543210`
     - 🇵🇰 Pakistan: `+923331234567`
     - 🇮🇷 Iran: `+989123456789`
     - 🇬🇧 UK: `+447700900123`
     - 🇦🇺 Australia: `+61412345678`
   - ⚠️ **Must start with + and country code**

### Buttons & Actions

#### **Button: 🔐 Send OTP**
- **Click when**: You've filled API ID, Hash, and Phone
- **What it does**: Sends verification code to your Telegram
- **Response**: Shows "OTP sent! Code expires in XXs"
- **Result**: Screen changes to Step 3

#### **Button: 🔄 Reset**
- **Click when**: You want to start over
- **What it does**: Clears all fields and resets the form
- **Result**: Returns to Step 1 with empty fields

---

### Step 3️⃣ - OTP Verification

#### **Input: Verification Code (OTP)**
- **What**: The code Telegram sends to your account
- **Where to find**: Open your Telegram app, check your saved messages or active chats
- **Format**: 5 digits (usually)
- **Example**: `12345`
- **Time limit**: ~5 minutes (expires quickly!)

#### **Button: ✅ Verify Code**
- **Click when**: You've entered the OTP code
- **What it does**: Verifies the code with Telegram
- **Possible responses**:
  - ✅ Success → Goes to My Accounts tab
  - ❌ Invalid code → Try again
  - ⏰ Code expired → Click "Reset" and request new code
  - 🔐 2FA needed → Goes to Step 4

#### **Button: 🔄 Reset**
- **Click when**: Code is wrong or expired
- **What it does**: Returns to Step 1

---

### Step 4️⃣ - Two-Factor Authentication (If Enabled)

#### **Input: 2FA Password**
- **What**: Your two-factor authentication password
- **Only appears if**: Your Telegram account has 2FA enabled
- **Format**: The password you set in Telegram settings
- **Example**: `MySecurePass123`

#### **Button: ✅ Verify 2FA**
- **Click when**: You've entered your 2FA password
- **What it does**: Verifies your 2FA password
- **Result**: 
  - ✅ Success → Account logged in!
  - ❌ Wrong password → Try again

#### **Button: 🔄 Reset**
- **Click when**: You want to start over

---

## 👤 Tab 2: MY ACCOUNTS (View Logged In Accounts)

### Purpose
See all your logged-in Telegram accounts and manage them.

### Display Information

For each account, you'll see:
- **📱 Phone Number** (e.g., `+1234567890`)
- **Status**: Account is active/logged in

### Available Buttons (Per Account)

#### **Button: 📋 View Info**
- **Click to**: Go to Account Info tab for this account
- **Shows**: Full account details and chats

#### **Button: 🚪 Logout**
- **Click to**: Disconnect this account
- **Result**: Account removed from logged-in list
- **Warning**: You'll need to login again to use it

### Example Screen
```
Logged In Accounts

┌─────────────────────────────────────┐
│ 📱 +1234567890                      │
│ [ 📋 View Info ]  [ 🚪 Logout ]    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 📱 +919876543210                    │
│ [ 📋 View Info ]  [ 🚪 Logout ]    │
└─────────────────────────────────────┘
```

---

## 📊 Tab 3: ACCOUNT INFO (View Details & Chats)

### Purpose
See detailed information about your account, profile, and all chats.

### Step 1: Select Account

#### **Dropdown: Select Account**
- **What**: Choose which account to view
- **Shows**: List of all logged-in accounts
- **Example options**:
  - `+1234567890`
  - `+919876543210`
  - `+923331234567`

---

### Step 2: View Account Information

After selecting an account, you'll see:

#### **Section: 👤 User Profile**

Three metrics displayed:

1. **User ID** - Unique Telegram ID
   - Example: `123456789`
   - What it is: Your unique identifier in Telegram

2. **Total Chats** - Number of chats/groups
   - Example: `47`
   - What it is: Private chats + groups combined

3. **Account Type** - User or Bot
   - Example: `👤 User`
   - Shows: 🤖 Bot (if bot account) or 👤 User (if person)

---

#### **Section: 📋 Details**

Two columns with your profile info:

**Left Column:**
- **First Name**: Your first name from Telegram
- **Last Name**: Your last name (if set)
- **Username**: Your Telegram handle (e.g., `@myusername`)

**Right Column:**
- **Phone**: Your Telegram phone number
- **Premium**: Shows if account has Telegram Premium
  - ✅ Yes (if premium)
  - ❌ No (if free)
- **Bio**: Your bio/about text

---

#### **Section: 💬 Chats & Groups**

Shows statistics in 3 boxes:

1. **Groups** - Number of group chats
   - Example: `12`

2. **Private Chats** - Number of 1-on-1 chats
   - Example: `35`

3. **Unread Messages** - Total unread count
   - Example: `5`

---

### Step 3: View All Chats Table

#### **Table: All Chats**

A data table showing:

| Chat Name | Type | Members | Unread |
|-----------|------|---------|--------|
| My Family | Group | 8 | 2 |
| Work Chat | Group | 45 | 0 |
| John Doe | Private | 0 | 1 |
| Support | Group | 120 | 5 |

**Columns explained:**
- **Chat Name**: Name of group or person's name
- **Type**: "Group" or "Private"
- **Members**: Number of people (0 for private chats)
- **Unread**: Number of unread messages

**Sorting**: Sorted by unread count (highest first)

---

## 🎯 Common Tasks

### Task 1: Login to Your First Account

```
1. Open app at http://localhost:8501
2. Go to "🔐 Login" tab
3. Get API ID & Hash from my.telegram.org
4. Enter: API ID, API Hash, Phone (+1234567890)
5. Click "🔐 Send OTP"
6. Enter the code from Telegram
7. (If 2FA enabled) Enter your 2FA password
8. ✅ Done! Account is logged in
```

### Task 2: Login Multiple Accounts

```
1. Follow Task 1 for first account
2. Still in Login tab, fill in new account details
3. Click "🔐 Send OTP" again
4. Verify new account with OTP/2FA
5. Go to "👤 My Accounts" to see both
```

### Task 3: View Account Details

```
1. Go to "📊 Account Info" tab
2. Select account from dropdown
3. See profile, chats, and statistics
```

### Task 4: Find Unread Messages

```
1. Go to "📊 Account Info" tab
2. Select account
3. Look at "💬 Chats & Groups" section
4. See "Unread Messages" metric
5. Scroll down to see which chats have unread
6. Sorted by unread count (highest first)
```

### Task 5: Logout from Account

```
1. Go to "👤 My Accounts" tab
2. Find the account you want to remove
3. Click "🚪 Logout"
4. Account is removed from list
```

---

## ⚠️ Troubleshooting Input Issues

### "❌ Please fill in all fields"
- **Cause**: You didn't enter API ID, Hash, or Phone
- **Fix**: Make sure all 3 fields have values

### "❌ Invalid phone number format"
- **Cause**: Phone doesn't include country code or has wrong format
- **Fix**: Use format `+CountryCodeNumber`
  - Correct: `+1234567890`
  - Wrong: `1234567890` (missing +)
  - Wrong: `9876543210` (missing country code)

### "⏰ OTP code expired"
- **Cause**: You took too long to enter code (>5 min)
- **Fix**: Click "Reset" and request new code

### "❌ Invalid OTP code"
- **Cause**: You entered wrong code
- **Fix**: Check Telegram again for correct code, type carefully

### "❌ Invalid 2FA password"
- **Cause**: Password is wrong or account doesn't have 2FA
- **Fix**: Check your Telegram Settings → Privacy & Security → 2-Step Verification

### "📭 No logged in accounts yet"
- **Cause**: You haven't logged in on Login tab
- **Fix**: Go to Login tab and complete login process first

---

## 🔐 Security Notes

### What Information is Used?

1. **API Credentials** (API ID & Hash)
   - Used to: Connect to Telegram servers
   - Stored: In session file locally (not sent anywhere)
   - Keep private: ✅ Yes, never share

2. **Phone Number**
   - Used to: Identify your account
   - Sent to: Telegram servers only
   - Keep private: ✅ Yes

3. **OTP Code**
   - Used to: Verify account ownership
   - Sent to: Telegram servers only
   - Temporary: ✅ Yes, expires in 5 min

4. **2FA Password**
   - Used to: Verify 2FA
   - Sent to: Telegram servers only
   - Never stored: ✅ Correct, only used once

### Storage Locations

```
~/.telegram_sessions/
├── session_1234567890
├── session_919876543210
└── session_923331234567
```

- Files encrypted when possible
- Only readable on YOUR computer
- Not uploaded anywhere

---

## 💡 Tips & Tricks

### Tip 1: Fast Account Switching
- Keep multiple accounts logged in
- Use "👤 My Accounts" to select which one to view

### Tip 2: Get Your API Credentials Once
- You can reuse same API ID & Hash for all accounts
- Store somewhere safe (not shared)

### Tip 3: Finding Groups
- Go to "📊 Account Info"
- Look at "Groups" metric
- Scroll table and look for "Type: Group"

### Tip 4: Check Notifications
- View → "💬 Chats & Groups" 
- See "Unread Messages" metric
- Table shows which chats have unread (sorted first)

### Tip 5: Account Status
- Look at "👤 My Accounts" to see all connected accounts
- Green status = logged in and ready
- Can manage multiple accounts at once

---

## 📞 Getting Help

### If Something Doesn't Work

1. **Check Requirements**
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify API Credentials**
   - Go to https://my.telegram.org/
   - Make sure API ID and Hash are correct
   - Try copying again (avoid typos)

3. **Check Internet Connection**
   - Telegram needs working internet
   - VPN might interfere

4. **Restart App**
   ```bash
   # Stop the app (Ctrl+C)
   streamlit run streamlit_app.py
   ```

5. **Clear Session (if stuck)**
   ```bash
   rm -rf ~/.telegram_sessions/
   # Then login again from scratch
   ```

---

## 🎓 Understanding the Flow

```
START
  │
  ├─→ [Tab 1: Login] ──→ Input: API ID + Hash + Phone
  │                      Click: "Send OTP"
  │                      Input: OTP Code
  │                      Click: "Verify"
  │                      (Optional) Input: 2FA Password
  │                      ✅ Login Success
  │
  ├─→ [Tab 2: My Accounts] ──→ View all logged-in accounts
  │                             Actions: View Info, Logout
  │
  └─→ [Tab 3: Account Info] ──→ Dropdown: Select account
                                Shows: Profile, Details, Chats
```

---

## 📋 Input Validation

| Input | Format | Required | Length | Allowed |
|-------|--------|----------|--------|---------|
| API ID | Number | Yes | Any | 0-9 |
| API Hash | String | Yes | 32 chars | a-z, 0-9 |
| Phone | +Country+Number | Yes | 10-15 | +, 0-9 |
| OTP | Numbers | Yes | 4-6 | 0-9 |
| 2FA | String | Optional | Any | Any |

---

**Now you're ready to use the Telegram Account Manager!** 🚀

Have questions? Check the [README.md](README.md) for more info.
