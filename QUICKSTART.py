#!/usr/bin/env python3
"""
TELEGRAM ACCOUNT MANAGER - QUICK START GUIDE

This script provides step-by-step instructions to set up and run the application.
"""

import os
import sys
from pathlib import Path

SETUP_GUIDE = """
╔════════════════════════════════════════════════════════════════════╗
║    📱 TELEGRAM ACCOUNT MANAGER - SETUP GUIDE                      ║
╚════════════════════════════════════════════════════════════════════╝

STEP 1: GET TELEGRAM API CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Visit: https://my.telegram.org/
2. Login with your phone number
3. Go to "API development tools"
4. Click "Create new application"
5. Fill the form and get:
   ✓ API_ID (numeric, e.g., 12345678)
   ✓ API_HASH (alphanumeric, e.g., a1b2c3d4e5f6...)

STEP 2: INSTALL DEPENDENCIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$ pip install -r requirements.txt

Required packages:
  • streamlit       - Web UI framework
  • telethon        - Telegram client library
  • python-dotenv   - Environment configuration
  • pandas          - Data handling
  • cryptography    - Credential encryption

STEP 3: CONFIGURE (OPTIONAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Create a .env file in project root (optional):

    API_ID=12345678
    API_HASH=a1b2c3d4e5f6...

Or enter them directly in the UI.

STEP 4: RUN THE APPLICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$ streamlit run streamlit_app.py

The app will open at: http://localhost:8501

STEP 5: LOGIN TO YOUR ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Go to "🔐 Login" tab
2. Enter API ID and API Hash
3. Enter your phone number (+1234567890)
4. Click "🔐 Send OTP"
5. Enter the OTP code from Telegram
6. (If enabled) Enter 2FA password
7. Click "✅ Verify & Login"

STEP 6: VIEW ACCOUNT INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Go to "📊 Account Info" tab to see:
  • User profile (ID, name, username)
  • Account status (premium, bot type)
  • All chats and groups
  • Unread message counts

TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ "Invalid phone number format"
   → Use: +CountryCodeNumber (e.g., +1234567890)

❌ "Too many login attempts"
   → Wait the specified time, then retry

❌ "OTP verification failed"
   → Codes expire after ~5 minutes
   → Request a new code if needed

❌ "Module not found" errors
   → Run: pip install -r requirements.txt

FEATURES OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Multiple Accounts   - Manage several Telegram accounts
✅ OTP Verification    - Secure login with 2FA support
✅ Account Info        - View profiles and statistics
✅ Chat Management     - See all chats, groups, and messages
✅ Local Storage       - All data stored locally (~/.telegram_sessions/)
✅ Secure             - Credentials encrypted when possible
✅ User-Friendly UI    - Clean Streamlit interface

SECURITY NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔒 Sessions stored locally at: ~/.telegram_sessions/
🔒 Never share your API credentials
🔒 Never share your .env file
🔒 Never share your 2FA password
🔒 Run only on trusted machines
🔒 Check .env is in .gitignore

FILE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Telegram-X/
├── streamlit_app.py       ← Main application (run this)
├── requirements.txt       ← Dependencies
├── README.md             ← Full documentation
├── QUICKSTART.py         ← This file
├── .env                  ← Configuration (create this)
├── .gitignore           ← Git ignore file
└── ~/.telegram_sessions/ ← Session storage (auto-created)

NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ✓ Get API credentials from my.telegram.org
2. ✓ Run: pip install -r requirements.txt
3. ✓ Run: streamlit run streamlit_app.py
4. ✓ Login and enjoy!

📚 DOCUMENTATION FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 README.md              - Full project documentation
📋 USAGE_GUIDE.md         - Complete feature guide with examples
🎯 QUICK_REFERENCE.md     - Quick reference for all inputs & buttons
🚀 QUICKSTART.py          - This file

Questions? Check USAGE_GUIDE.md for detailed instructions.

═══════════════════════════════════════════════════════════════════════
Made with ❤️  using Streamlit & Telethon
═══════════════════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    print(SETUP_GUIDE)
