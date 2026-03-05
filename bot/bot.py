import os
import json
import time
from flask import Flask, request
import requests

app = Flask(__name__)

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = '8518993595:AAGuZ7NIW_FRuThokONbn1O4KZHn5VOprmE'
TELEGRAM_CHAT_ID = '5223827419'
WALLETS_FILE = 'wallets.json'

ALCHEMY_AUTH_TOKEN = 'lkuum_adtYB-St4UTVu2c77DXSc9u1Rp'
ETH_WEBHOOK_ID = 'wh_uyd51wlbu7540kry'
SOL_WEBHOOK_ID = 'wh_8eh89f31sewteqbi'

SOLANA_RPC_URL = "https://solana-mainnet.g.alchemy.com/v2/VdMiCdsw9fyieYfs-JwSW"

PROCESSED_TXS = []

COMMON_TOKENS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "So11111111111111111111111111111111111111112": "WSOL",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk": "WEN",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbAbdRhAwapKE": "JUP"
}

COINGECKO_IDS = {
    "ETH": "ethereum",
    "SOL": "solana",
    "WSOL": "solana",
    "USDC": "usd-coin",
    "USDT": "tether",
    "BONK": "bonk",
    "WEN": "wen-4",
    "JUP": "jupiter-exchange-solana"
}

def get_fiat_value(symbol, amount):
    if symbol not in COINGECKO_IDS: return ""
    cg_id = COINGECKO_IDS[symbol]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd,inr"
    try:
        res = requests.get(url, timeout=3).json()
        usd_price = res[cg_id]['usd']
        inr_price = res[cg_id]['inr']
        total_usd = usd_price * abs(amount)
        total_inr = inr_price * abs(amount)
        if total_usd < 0.01: return ""
        return f" <i>(${total_usd:,.2f} | ₹{total_inr:,.0f})</i>"
    except Exception as e:
        print(f"⚠️ CoinGecko Error: {e}")
        return ""

def load_wallets():
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE, 'r') as f: return json.load(f)
    return {}

def save_wallets(wallets):
    with open(WALLETS_FILE, 'w') as f: json.dump(wallets, f, indent=4)

def format_wallet(address):
    wallets = load_wallets()
    if address in wallets: return wallets[address]
    if len(address) > 12: return f"<code>{address[:6]}...{address[-4:]}</code>"
    return f"<code>{address}</code>"

def send_telegram_alert(message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    }
    if reply_markup: payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

def update_alchemy_radar(address, action="add"):
    webhook_id = ETH_WEBHOOK_ID if address.startswith("0x") else SOL_WEBHOOK_ID
    url = "https://dashboard.alchemy.com/api/update-webhook-addresses"
    headers = {"Content-Type": "application/json", "X-Alchemy-Token": ALCHEMY_AUTH_TOKEN}
    payload = {
        "webhook_id": webhook_id,
        "addresses_to_add": [address] if action == "add" else [],
        "addresses_to_remove": [address] if action == "remove" else []
    }
    return requests.patch(url, json=payload, headers=headers).status_code == 200

def get_full_solana_tx(signature, retries=5):
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    for attempt in range(retries):
        try:
            response = requests.post(SOLANA_RPC_URL, json=payload, headers=headers)
            data = response.json()
            if data.get('result'): return data.get('result')
            if response.status_code == 429:
                time.sleep(2)
                continue
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return {}

@app.route('/telegram', methods=['POST'])
def handle_telegram():
    data = request.json
    if not data or 'message' not in data: return "OK", 200
    chat_id = str(data['message']['chat']['id'])
    text = data['message'].get('text', '')
    if chat_id != TELEGRAM_CHAT_ID: return "Unauthorized", 403
    wallets = load_wallets()

    if text.startswith('/add'):
        parts = text.split(' ', 2)
        if len(parts) >= 3:
            addr, name = parts[1], parts[2]
            if update_alchemy_radar(addr, "add"):
                wallets[addr] = name
                save_wallets(wallets)
                chain = "Ethereum" if addr.startswith("0x") else "Solana"
                send_telegram_alert(f"✅ <b>Whale Locked In!</b>\n\n<b>Name:</b> {name}\n<b>Wallet:</b> <code>{addr}</code>\n\n🌐 <i>Synced with Alchemy {chain} Radar!</i>")
            else: send_telegram_alert("❌ <b>API Error:</b> Failed to sync with Alchemy.")
        else: send_telegram_alert("❌ <b>Format error.</b> Type it like this:\n<code>/add [address] [name]</code>")

    elif text.startswith('/remove'):
        parts = text.split(' ', 1)
        if len(parts) == 2:
            addr = parts[1]
            if addr in wallets:
                update_alchemy_radar(addr, "remove")
                del wallets[addr]
                save_wallets(wallets)
                send_telegram_alert(f"🗑️ <b>Radar Cleared. Removed:</b>\n<code>{addr}</code>")
            else: send_telegram_alert("❌ Wallet not found in your list.")
        else: send_telegram_alert("❌ <b>Format error.</b> Type it like this:\n<code>/remove [address]</code>")

    elif text.startswith('/list'):
        if not wallets: send_telegram_alert("📂 Your Watchlist is empty.")
        else:
            msg = "📂 <b>Your Active Watchlist:</b>\n\n"
            for addr, name in wallets.items(): msg += f"• {name} (<code>{addr[:6]}...{addr[-4:]}</code>)\n"
            send_telegram_alert(msg)

    return "OK", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    global PROCESSED_TXS
    data = request.json
    try:
        event = data.get('event', {})
        wallets = load_wallets()
        
        # --- ETHEREUM HANDLING ---
        if 'activity' in event:
            for tx in event.get('activity', []):
                tx_hash = tx.get('hash', '')
                asset = tx.get('asset', 'UNKNOWN')
                value = tx.get('value', 0)
                
                # Filter out dust and empty hashes immediately
                if not tx_hash or value == 0 or value is None: continue

                # 🧠 SMART MEMORY: Remember the exact transfer, not just the generic hash
                activity_id = f"{tx_hash}_{asset}_{value}"
                
                if activity_id in PROCESSED_TXS: continue
                PROCESSED_TXS.append(activity_id)
                if len(PROCESSED_TXS) > 100: PROCESSED_TXS.pop(0)

                from_addr = tx.get('fromAddress', 'Unknown')
                to_addr = tx.get('toAddress', 'Unknown')
                
                fiat_str = get_fiat_value(asset, value)
                
                msg = (f"🔵 <b>ETH ACTIVITY ALERT</b> 🔵\n\n"
                       f"💰 <b>Amount:</b> {value} {asset}{fiat_str}\n"
                       f"📤 <b>From:</b> {format_wallet(from_addr)}\n"
                       f"📥 <b>To:</b> {format_wallet(to_addr)}")
                
                markup = {
                    "inline_keyboard": [
                        [{"text": "🔍 View on Etherscan", "url": f"https://etherscan.io/tx/{tx_hash}"}],
                        [{"text": "🕵️‍♂️ Inspect on DeBank", "url": f"https://debank.com/profile/{from_addr}"}]
                    ]
                }
                
                send_telegram_alert(msg, reply_markup=markup)
                print(f"✅ ETH Alert sent with live prices for {tx_hash}!")

        # --- SOLANA HANDLING ---
        elif 'transaction' in event:
            for tx in event.get('transaction', []):
                tx_hash = tx.get('signature', '')
                if not tx_hash: continue
                
                if tx_hash in PROCESSED_TXS: continue
                PROCESSED_TXS.append(tx_hash)
                if len(PROCESSED_TXS) > 100: PROCESSED_TXS.pop(0)

                print(f"\n🚨 [TRIPWIRE TRIGGERED] TX: {tx_hash}")
                time.sleep(2) 
                
                full_tx = get_full_solana_tx(tx_hash)
                if not full_tx: continue
                    
                meta = full_tx.get('meta', {})
                if not meta: continue
                
                msg_data = full_tx.get('transaction', {}).get('message', {})
                account_keys = msg_data.get('accountKeys', [])
                
                tracked_wallet = None
                wallet_index = -1
                for i, account in enumerate(account_keys):
                    key_str = account.get('pubkey') if isinstance(account, dict) else account
                    if key_str in wallets:
                        tracked_wallet = key_str
                        wallet_index = i
                        break
                        
                if not tracked_wallet: continue
                
                changes_detected = []
                token_balances = {}
                
                pre_sol = meta.get('preBalances', [])
                post_sol = meta.get('postBalances', [])
                if wallet_index != -1 and wallet_index < len(pre_sol) and wallet_index < len(post_sol):
                    sol_change = (post_sol[wallet_index] - pre_sol[wallet_index]) / 1_000_000_000
                    if abs(sol_change) > 0.005:
                        sign = "+" if sol_change > 0 else ""
                        fiat_str = get_fiat_value("SOL", sol_change)
                        changes_detected.append(f"<b>Native SOL:</b> {sign}{sol_change:.4f} SOL{fiat_str}")

                pre_tokens = meta.get('preTokenBalances', [])
                post_tokens = meta.get('postTokenBalances', [])
                
                for bal in pre_tokens:
                    if bal.get('owner') == tracked_wallet:
                        amt = bal.get('uiTokenAmount', {}).get('uiAmount') or 0
                        token_balances[bal.get('mint')] = -amt
                        
                for bal in post_tokens:
                    if bal.get('owner') == tracked_wallet:
                        amt = bal.get('uiTokenAmount', {}).get('uiAmount') or 0
                        mint = bal.get('mint')
                        token_balances[mint] = token_balances.get(mint, 0) + amt

                for mint, change in token_balances.items():
                    if abs(change) > 0.0001:
                        sign = "+" if change > 0 else ""
                        token_name = COMMON_TOKENS.get(mint, f"Token ({mint[:4]}...{mint[-4:]})")
                        fiat_str = get_fiat_value(token_name, change)
                        changes_detected.append(f"<b>Token:</b> {sign}{change:,.2f} {token_name}{fiat_str}")

                if changes_detected:
                    action_text = "\n".join(changes_detected)
                    msg = (f"🟣 <b>SOL WHALE ACTIVITY</b> 🟣\n\n"
                           f"🎯 <b>Wallet:</b> {format_wallet(tracked_wallet)}\n\n"
                           f"⚡ <b>Balance Changes:</b>\n{action_text}")
                    
                    markup = {
                        "inline_keyboard": [
                            [{"text": "🔍 View on Solscan", "url": f"https://solscan.io/tx/{tx_hash}"}],
                            [{"text": "🦅 DexScreener Profile", "url": f"https://dexscreener.com/solana/{tracked_wallet}"}]
                        ]
                    }
                    
                    send_telegram_alert(msg, reply_markup=markup)
                    print(f"✅ Alert sent with live prices!")
                    
        return "Webhook received!", 200
    except Exception as e:
        import traceback
        print(f"❌ Error during scan:\n{traceback.format_exc()}")
        return "Error", 500

if __name__ == '__main__':
    print("🚀 Premium UI Bot Active! Fetching live USD & INR prices...")
    app.run(port=5000)