# 📱 Telegram Account Manager

A modern Streamlit-based UI for managing Telegram accounts with login, authentication, and account information retrieval.

## ✨ Features

- 🔐 **Secure Login** - Login to Telegram using API credentials (ID & Hash)
- 📱 **OTP Verification** - Automatic OTP handling with 2FA support
- 👤 **Multiple Accounts** - Manage multiple Telegram accounts simultaneously
- 📊 **Account Information** - View detailed user profile and statistics
- 💬 **Chat Management** - See all chats, groups, and unread messages
- 🔒 **Privacy First** - All sessions stored locally, no external data sharing

## 🚀 Quick Start

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/zaradar1/Telegram-X.git
cd Telegram-X
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Get Telegram API Credentials:**
   - Visit [my.telegram.org](https://my.telegram.org/)
   - Login with your phone number
   - Create an app to get your **API ID** and **API Hash**

### Running the Application

```bash
streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`

## 📖 Usage Guide

### Step 1: Login Tab 🔐

1. Enter your **API ID** from my.telegram.org
2. Enter your **API Hash** from my.telegram.org
3. Enter your **Phone Number** (with country code, e.g., +1234567890)
4. Click **"🔐 Send OTP"** button
5. Enter the **Verification Code** sent to your Telegram
6. (If enabled) Enter your **2FA Password**
7. Click **"✅ Verify & Login"**

### Step 2: My Accounts Tab 👤

- View all logged-in accounts
- See phone numbers and login status
- Quick access to view account information
- Logout from any account

### Step 3: Account Info Tab 📊

- **User Profile**: View basic account details
  - User ID
  - Total Chats
  - Account Type (User/Bot)
  - Name, Username, Phone

- **Account Details**: Extended information
  - First/Last Name
  - Username (@handle)
  - Phone Number
  - Premium Status
  - Bio/About

- **Chats & Groups**: Message statistics
  - Number of Groups
  - Number of Private Chats
  - Unread Messages Count
  - Detailed chat table with names, types, members, and unread counts

## 🔒 Security

- ✅ All sessions stored locally in `~/.telegram_sessions/`
- ✅ Credentials encrypted with Fernet (if available)
- ✅ No data sent to external servers
- ✅ 2FA support for extra security

## 🛠️ Configuration

Create a `.env` file in the project root to configure:

```env
API_ID=your_api_id
API_HASH=your_api_hash
FERNET_KEY=auto_generated_or_set_yours
```

## 📋 Requirements

- Python 3.8+
- Telegram Account
- API Credentials from [my.telegram.org](https://my.telegram.org/)

## 🐛 Troubleshooting

### "Invalid phone number format"
- Use format: `+CountryCodePhoneNumber`
- Example: `+1234567890` for US

### "Too many login attempts"
- Wait the specified time before trying again
- Use different API credentials if the issue persists

### "Flood wait error"
- Telegram is rate-limiting your requests
- Wait a few minutes and try again

### "OTP verification failed"
- Make sure you enter the correct code
- The code expires after a few minutes
- Request a new code if it expires

## 📦 Project Structure

```
Telegram-X/
├── streamlit_app.py      # Main Streamlit application
├── requirements.txt      # Python dependencies
├── .env                  # Configuration file (create this)
├── terabox_v5.db        # Database (auto-created)
└── README.md            # This file
```

## 📝 API Used

- **Telethon** - Telegram client library for Python
- **Streamlit** - Web UI framework
- **Cryptography** - Credential encryption

## 🔗 Resources

- [Telethon Documentation](https://docs.telethon.dev/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Get Telegram API Credentials](https://my.telegram.org/)

## ⚠️ Disclaimer

This tool is for personal use only. Ensure you comply with Telegram's Terms of Service and applicable laws in your jurisdiction.

## 📄 License

This project is open source and available under the MIT License.

## 🤝 Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Made with ❤️ using Streamlit & Telethon**
