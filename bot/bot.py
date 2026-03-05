import os
import json
import time
from flask import Flask, request
import requests

app = Flask(__name__)

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = '8518993595:AAGuZ7NIW_FRuThokONbn1O4KZHn5VOprmE'
TELEGRAM_CHAT_ID = '5223827419'
WALLETS_FILE = 'wallets.json'
SOLANA_RPC_URL = "https://solana-mainnet.g.alchemy.com/v2/VdMiCdsw9fyieYfs-JwSW"

# Fixed Pricing IDs for CoinGecko
COINGECKO_IDS = {
    "ETH": "ethereum",
    "SOL": "solana",
    "USDC": "usd-coin",
    "USDT": "tether",
    "BONK": "bonk",
    "JUP": "jupiter-exchange-solana"
}

PROCESSED_TXS = []

def get_fiat_value(symbol, amount):
    cg_id = COINGECKO_IDS.get(symbol)
    if not cg_id: return ""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd,inr"
    try:
        res = requests.get(url, timeout=5).json()
        if cg_id in res:
            usd = res[cg_id].get('usd', 0) * abs(amount)
            inr = res[cg_id].get('inr', 0) * abs(amount)
            return f" <i>($ {usd:,.2f} | ₹ {inr:,.0f})</i>"
        return ""
    except: return ""

def load_wallets():
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE, 'r') as f: return json.load(f)
    return {}

def format_wallet(address, wallets):
    if address in wallets: return f"<b>{wallets[address]}</b>"
    return f"<code>{address[:6]}...{address[-4:]}</code>"

def send_telegram(msg, markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup: payload["reply_markup"] = markup
    requests.post(url, json=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    global PROCESSED_TXS
    data = request.json
    event = data.get('event', {})
    wallets = load_wallets()

    # --- ETH HANDLING ---
    if 'activity' in event:
        for tx in event['activity']:
            tx_hash = tx.get('hash')
            if not tx_hash or tx_hash in PROCESSED_TXS: continue
            PROCESSED_TXS.append(tx_hash)
            
            asset = tx.get('asset', 'ETH')
            val = tx.get('value', 0)
            if val < 0.001: continue # Skip dust
            
            fiat = get_fiat_value(asset, val)
            msg = (f"🔵 <b>ETH MOVEMENT</b> 🔵\n\n"
                   f"💰 {val} {asset}{fiat}\n"
                   f"📤 From: {format_wallet(tx.get('fromAddress'), wallets)}\n"
                   f"📥 To: {format_wallet(tx.get('toAddress'), wallets)}")
            
            kb = {"inline_keyboard": [[{"text": "🔍 Etherscan", "url": f"https://etherscan.io/tx/{tx_hash}"}]]}
            send_telegram(msg, kb)

    # --- SOL HANDLING ---
    elif 'transaction' in event:
        for tx in event['transaction']:
            sig = tx.get('signature')
            if not sig or sig in PROCESSED_TXS: continue
            PROCESSED_TXS.append(sig)
            
            print(f"🚨 [TRIPWIRE] {sig}")
            time.sleep(2) # Wait for blockchain update
            
            res = requests.post(SOLANA_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }).json().get('result')

            if not res: continue
            meta = res.get('meta', {})
            
            # Identify which tracked wallet is involved
            keys = res.get('transaction', {}).get('message', {}).get('accountKeys', [])
            tracked = next((k.get('pubkey') if isinstance(k, dict) else k for k in keys if (k.get('pubkey') if isinstance(k, dict) else k) in wallets), None)
            
            if tracked:
                # Calculate SOL Change
                idx = next(i for i, k in enumerate(keys) if (k.get('pubkey') if isinstance(k, dict) else k) == tracked)
                change = (meta.get('postBalances', [])[idx] - meta.get('preBalances', [])[idx]) / 1e9
                
                if abs(change) > 0.01:
                    fiat = get_fiat_value("SOL", change)
                    msg = (f"🟣 <b>SOL MOVEMENT</b> 🟣\n\n"
                           f"🎯 Wallet: <b>{wallets[tracked]}</b>\n"
                           f"⚡ Change: {change:+.4f} SOL{fiat}")
                    kb = {"inline_keyboard": [[{"text": "🔍 Solscan", "url": f"https://solscan.io/tx/{sig}"}]]}
                    send_telegram(msg, kb)
                    
    if len(PROCESSED_TXS) > 200: PROCESSED_TXS.pop(0)
    return "OK", 200

if __name__ == '__main__':
    app.run(port=10000)
