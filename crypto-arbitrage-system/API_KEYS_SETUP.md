# 🔑 API Keys Setup Guide

This system uses **only 2 exchanges** with implemented adapters:

## ✅ Implemented Exchanges

1. **Kraken** (Priority 1)
2. **Coinbase Advanced** (Priority 2)

---

## 🛡️ Security Requirements

Since you're running in **paper trading mode**, you should:

- ✅ **Use READ-ONLY API keys** (no trading permissions)
- ✅ **Enable IP whitelisting** if available
- ✅ **Never commit `.env` to git** (already in `.gitignore`)
- ✅ **Rotate keys regularly** (every 90 days recommended)

---

## 📋 Step-by-Step Setup

### 1. Kraken API Key

**URL:** https://www.kraken.com/u/security/api

**Steps:**
1. Log in to Kraken
2. Go to Settings → API → Create API Key
3. **Permissions** (CHECK THESE ONLY):
   - ✅ Query Funds
   - ✅ Query Open Orders & Trades
   - ✅ Query Closed Orders & Trades
   - ✅ Query Ledger Entries
   - ❌ Create & Modify Orders (DO NOT CHECK)
   - ❌ Cancel/Close Orders (DO NOT CHECK)
   - ❌ Withdraw Funds (DO NOT CHECK)
4. (Optional) Add IP whitelist for extra security
5. Click "Generate Key"
6. Copy your **API Key** and **Private Key**

### 2. Coinbase Advanced API Key

**URL:** https://www.coinbase.com/settings/api

**Steps:**
1. Log in to Coinbase
2. Go to Settings → API
3. Click "New API Key"
4. Select **Advanced Trade API**
5. **Permissions** (CHECK THESE ONLY):
   - ✅ View (read-only access)
   - ❌ Trade (DO NOT CHECK for paper trading)
   - ❌ Transfer (DO NOT CHECK)
6. (Optional) Add IP whitelist
7. Click "Create"
8. **IMPORTANT:** Copy your API Key and Secret immediately - you won't see them again!

---

## 🔧 Adding Keys to .env File

Open `crypto-arbitrage-system/.env` and replace the placeholder values:

```bash
# Before
KRAKEN_API_KEY=your_kraken_api_key_here
KRAKEN_API_SECRET=your_kraken_api_secret_here

COINBASE_ADVANCED_API_KEY=your_coinbase_api_key_here
COINBASE_ADVANCED_API_SECRET=your_coinbase_api_secret_here

# After (example - use your actual keys)
KRAKEN_API_KEY=ABC123xyz789...
KRAKEN_API_SECRET=DEF456abc012...

COINBASE_ADVANCED_API_KEY=organizations/abc123/apiKeys/xyz789
COINBASE_ADVANCED_API_SECRET=-----BEGIN EC PRIVATE KEY-----\nMHc...
```

**Notes:**
- Kraken secret is a long base64 string
- Coinbase API key starts with `organizations/`
- Coinbase secret is a multi-line EC private key (keep the `\n` newlines)

---

## ✅ Testing Connection

After adding your keys, test the connection:

```bash
cd crypto-arbitrage-system
python scripts/integration_test.py
```

**Expected Output:**
- ✅ Configuration Loading
- ✅ Exchange Initialization (Kraken)
- ✅ Exchange Initialization (Coinbase Advanced)
- ✅ Exchange Connectivity (should PASS with real keys)

---

## 🚨 Troubleshooting

### "Invalid API Key"
- Double-check you copied the entire key (no extra spaces)
- Ensure key is for the correct exchange
- Check key hasn't been deleted on exchange website

### "Permission Denied"
- Verify you enabled "Query Funds" / "View" permissions
- For Kraken, make sure "Query Open/Closed Orders" is checked

### "IP Not Whitelisted"
- If you enabled IP whitelisting, add your current IP
- You can find your IP at: https://whatismyipaddress.com

### "Invalid Signature"
- For Kraken: Check secret is complete base64 string
- For Coinbase: Ensure private key includes BEGIN/END markers

---

## 📊 Next Steps

Once API keys are working:

1. Run integration tests: `python scripts/integration_test.py`
2. Start paper trading: `python src/main.py`
3. Monitor for 48+ hours to validate strategy
4. Review P&L and risk metrics daily
5. Only move to live trading after consistent results

---

## ⚠️ IMPORTANT WARNINGS

- **NEVER** share your API keys publicly
- **NEVER** commit `.env` to git
- **NEVER** enable trading permissions until you're ready for live trading
- **ALWAYS** start with paper trading mode first
- **ALWAYS** test with small amounts when going live

