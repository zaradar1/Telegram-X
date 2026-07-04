# 🎯 Quick Reference Card

## All Inputs & Buttons at a Glance

### 🔐 LOGIN TAB

#### Inputs (Step 1)
| Field | Type | Format | Example |
|-------|------|--------|---------|
| API ID | Number | Digits only | `12345678` |
| API Hash | Password | 32 chars | `a1b2c3d4e5f6...` |
| Phone | Text | +CountryCode+Number | `+1234567890` |

#### Buttons (Step 1)
| Button | Action |
|--------|--------|
| 🔐 Send OTP | Request verification code |
| 🔄 Reset | Clear form and start over |

#### Inputs (Step 3 - After OTP sent)
| Field | Type | Format | Example |
|-------|------|--------|---------|
| Verification Code | Text | 4-6 digits | `12345` |

#### Buttons (Step 3)
| Button | Action |
|--------|--------|
| ✅ Verify Code | Submit OTP code |
| 🔄 Reset | Start over |

#### Inputs (Step 4 - If 2FA enabled)
| Field | Type | Format | Example |
|-------|------|--------|---------|
| 2FA Password | Password | Your password | `MyPass123` |

#### Buttons (Step 4)
| Button | Action |
|--------|--------|
| ✅ Verify 2FA | Submit 2FA password |
| 🔄 Reset | Start over |

---

### 👤 MY ACCOUNTS TAB

#### Display
- Shows all logged-in accounts
- Each account shows: Phone number + Buttons

#### Buttons (Per Account)
| Button | Action |
|--------|--------|
| 📋 View Info | Go to account details |
| 🚪 Logout | Disconnect account |

---

### 📊 ACCOUNT INFO TAB

#### Inputs (Always)
| Control | Type | Shows |
|---------|------|-------|
| Select Account | Dropdown | List of accounts |

#### Displays (After selecting account)

**1. User Profile**
- User ID (number)
- Total Chats (count)
- Account Type (User/Bot)

**2. Details**
- First Name
- Last Name  
- Username
- Phone
- Premium Status (Yes/No)
- Bio

**3. Chats & Groups**
- Groups count
- Private Chats count
- Unread Messages count

**4. All Chats Table**
- Chat Name
- Type (Group/Private)
- Members
- Unread

---

## Country Code Examples

```
🇮🇳 India           +91
🇵🇰 Pakistan        +92
🇮🇷 Iran            +98
🇬🇧 UK              +44
🇺🇸 USA/Canada      +1
🇦🇺 Australia       +61
🇧🇩 Bangladesh      +880
🇪🇬 Egypt           +20
🇲🇪 Mexico          +52
```

---

## Error Messages & Solutions

| Error | Cause | Fix |
|-------|-------|-----|
| ❌ Please fill in all fields | Missing API ID/Hash/Phone | Enter all 3 fields |
| ❌ Invalid phone number format | Wrong format | Use `+CountryNumber` |
| ⏱️ Too many attempts | Flooded API | Wait X seconds |
| ⏰ OTP code expired | Took >5 min to enter | Click Reset, get new code |
| ❌ Invalid OTP code | Wrong code | Check Telegram, try again |
| ❌ Invalid 2FA password | Wrong password | Check your settings |
| 🚫 Phone number banned | Account issues | Contact Telegram support |

---

## Step-by-Step: First Login

```
1. Run app:              streamlit run streamlit_app.py
2. Open browser:         http://localhost:8501
3. Get credentials:      Visit my.telegram.org
4. Open Login tab:       Click "🔐 Login" tab
5. Enter API ID:         e.g., 12345678
6. Enter API Hash:       e.g., a1b2c3d4e5f6...
7. Enter Phone:          e.g., +1234567890
8. Click Send OTP:       Click "🔐 Send OTP" button
9. Get code from TG:     Check Telegram app
10. Enter OTP:           e.g., 12345
11. Click Verify:        Click "✅ Verify Code" button
12. (If 2FA) Enter pwd:  Enter your 2FA password
13. (If 2FA) Click:      Click "✅ Verify 2FA" button
14. ✅ Done:             Account logged in!
```

---

## Step-by-Step: View Account Info

```
1. Go to Account Info:   Click "📊 Account Info" tab
2. Select account:       Choose from dropdown
3. See profile:          User Profile section
4. See details:          Details section
5. See statistics:       Chats & Groups section
6. See all chats:        Scroll down for table
```

---

## Keyboard Shortcuts (Streamlit)

```
Ctrl+C              Stop the app
Ctrl+R              Refresh browser
R (in terminal)     Clear all Streamlit cache
```

---

## Common Phone Number Formats

| Country | Example | Correct |
|---------|---------|---------|
| USA | 2125551234 | +12125551234 |
| India | 9876543210 | +919876543210 |
| Pakistan | 3001234567 | +923001234567 |
| Iran | 9123456789 | +989123456789 |

---

## Where to Find Each Input

### API Credentials
- **Where**: my.telegram.org → API development tools
- **Steps**: 
  1. Visit https://my.telegram.org/
  2. Login with phone
  3. Go to "API development tools"
  4. Click "Create new application"
  5. Copy API ID and App api_hash

### OTP Code
- **Where**: Telegram app
- **Look in**: Saved Messages or active chats
- **How to find**: Open Telegram, look for sent code
- **Expires in**: ~5 minutes

### 2FA Password
- **Where**: Your Telegram account settings
- **Set at**: Settings → Privacy & Security → 2-Step Verification
- **Only needed if**: You enabled 2FA on your account

---

## File Structure

```
streamlit_app.py       Main app (370 lines)
requirements.txt       Dependencies
README.md             Full documentation
QUICKSTART.py         Setup instructions
USAGE_GUIDE.md        This detailed guide
```

---

## Quick Commands

### Install
```bash
pip install -r requirements.txt
```

### Run
```bash
streamlit run streamlit_app.py
```

### Clear Sessions
```bash
rm -rf ~/.telegram_sessions/
```

### Check Python
```bash
python3 --version
pip --version
```

---

**Print this page or save as reference while using the app!** 📄
