import os
import json
import time
import threading
from flask import Flask, request
import requests
import sys

app = Flask(__name__)

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = '8518993595:AAGuZ7NIW_FRuThokONbn1O4KZHn5VOprmE'
TELEGRAM_CHAT_ID = '5223827419'
SOLANA_RPC_URL = "https://solana-mainnet.g.alchemy.com/v2/VdMiCdsw9fyieYfs-JwSW"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

COMMON_TOKENS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "So11111111111111111111111111111111111111112": "WSOL",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk": "WEN",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbAbdRhAwapKE": "JUP"
}

COINGECKO_IDS = {
    "ETH": "ethereum", "SOL": "solana", "USDC": "usd-coin",
    "USDT": "tether", "BONK": "bonk", "JUP": "jupiter-exchange-solana"
}

PROCESSED_TXS = []
HL_LAST_TIMESTAMPS = {}

def get_fiat_value(symbol, amount):
    cg_id = COINGECKO_IDS.get(symbol)
    if not cg_id: return ""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd,inr"
    try:
        res = requests.get(url, timeout=5).json()
        if cg_id in res:
            usd = res[cg_id].get('usd', 0) * abs(amount)
            inr = res[cg_id].get('inr', 0) * abs(amount)
            if usd < 0.01: return ""
            return f" <i>($ {usd:,.2f} | ₹ {inr:,.0f})</i>"
        return ""
    except: return ""

def load_wallets():
    paths_to_try = [
        os.path.join(BASE_DIR, 'wallets.json'),
        os.path.join(os.path.dirname(BASE_DIR), 'wallets.json')
    ]
    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    return {}

def format_wallet(address, wallets):
    if address in wallets: return f"<b>{wallets[address]}</b>"
    return f"<code>{address[:6]}...{address[-4:]}</code>"

def send_telegram(msg, markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup: payload["reply_markup"] = markup
    requests.post(url, json=payload)

# --- BRAIN 2: HYPERLIQUID SPY ---
def hyperliquid_spy():
    print("🕵️‍♂️ Hyperliquid Spy Thread Started!", flush=True)
    while True:
        try:
            wallets = load_wallets()
            for address, name in wallets.items():
                if not address.startswith("0x"): 
                    continue
                
                url = "https://api.hyperliquid.xyz/info"
                payload = {"type": "userFills", "user": address}
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=5).json()
                
                if not isinstance(res, list) or len(res) == 0:
                    continue
                
                for fill in reversed(res[:5]): 
                    fill_time = fill.get("time", 0)
                    
                    if address not in HL_LAST_TIMESTAMPS:
                        HL_LAST_TIMESTAMPS[address] = fill_time
                        continue 
                    
                    if fill_time > HL_LAST_TIMESTAMPS[address]:
                        HL_LAST_TIMESTAMPS[address] = fill_time
                        
                        coin = fill.get("coin", "UNKNOWN")
                        dir_str = fill.get("dir", "Trade")
                        sz = fill.get("sz", "0")
                        px = fill.get("px", "0")
                        pnl = fill.get("closedPnl", "0")
                        
                        pnl_str = f"\n💸 <b>Realized PnL:</b> ${float(pnl):,.2f}" if float(pnl) != 0 else ""
                        
                        msg = (f"🌊 <b>HYPERLIQUID WHALE</b> 🌊\n\n"
                               f"🎯 <b>Wallet:</b> <b>{name}</b>\n"
                               f"⚡ <b>Action:</b> {dir_str} {sz} {coin}\n"
                               f"💰 <b>Price:</b> ${float(px):,.4f}{pnl_str}")
                               
                        kb = {"inline_keyboard": [[{"text": "📊 View HL Profile", "url": f"https://app.hyperliquid.xyz/explorer/address/{address}"}]]}
                        send_telegram(msg, kb)
                        print(f"✅ HL Alert Sent for {name}!", flush=True)
                        
            time.sleep(15) 
        except Exception as e:
            time.sleep(15)

# --- START THE SPY THREAD FOR CLOUD DEPLOYMENTS ---
# Placing this OUTSIDE the main block so Gunicorn catches it instantly
threading.Thread(target=hyperliquid_spy, daemon=True).start()

# --- BRAIN 1: TELEGRAM & ALCHEMY DOORS ---
@app.route('/telegram', methods=['POST'])
def handle_telegram():
    # Restored Telegram Door to prevent 404 errors!
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    global PROCESSED_TXS
    data = request.json
    event = data.get('event', {})
    wallets = load_wallets()

    if 'activity' in event:
        for tx in event['activity']:
            tx_hash = tx.get('hash')
            if not tx_hash or tx_hash in PROCESSED_TXS: continue
            PROCESSED_TXS.append(tx_hash)
            
            asset = tx.get('asset', 'ETH')
            val = tx.get('value', 0)
            if val < 0.0001: continue
            
            fiat = get_fiat_value(asset, val)
            msg = (f"🔵 <b>ETH MOVEMENT</b> 🔵\n\n"
                   f"💰 {val} {asset}{fiat}\n"
                   f"📤 From: {format_wallet(tx.get('fromAddress'), wallets)}\n"
                   f"📥 To: {format_wallet(tx.get('toAddress'), wallets)}")
            
            kb = {"inline_keyboard": [[{"text": "🔍 Etherscan", "url": f"https://etherscan.io/tx/{tx_hash}"}]]}
            send_telegram(msg, kb)

    elif 'transaction' in event:
        for tx in event['transaction']:
            sig = tx.get('signature')
            if not sig or sig in PROCESSED_TXS: continue
            PROCESSED_TXS.append(sig)
            
            print(f"🚨 [TRIPWIRE TRIGGERED] {sig}", flush=True)
            
            res = None
            for i in range(5):
                time.sleep(2)
                try:
                    response = requests.post(SOLANA_RPC_URL, json={
                        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    }).json()
                    res = response.get('result')
                    if res: break
                except: pass

            if not res: continue
            
            meta = res.get('meta', {})
            keys = res.get('transaction', {}).get('message', {}).get('accountKeys', [])
            
            tracked = None
            tracked_idx = None
            
            for i, k in enumerate(keys):
                pk = k.get('pubkey') if isinstance(k, dict) else k
                if pk in wallets:
                    tracked = pk
                    tracked_idx = i
                    break
            
            if not tracked:
                all_bals = meta.get('preTokenBalances', []) + meta.get('postTokenBalances', [])
                for bal in all_bals:
                    owner = bal.get('owner')
                    if owner in wallets:
                        tracked = owner
                        break

            if not tracked: continue
            
            changes_detected = []
            token_balances = {}

            if tracked_idx is not None:
                pre_sol = meta.get('preBalances', [])[tracked_idx]
                post_sol = meta.get('postBalances', [])[tracked_idx]
                sol_change = (post_sol - pre_sol) / 1e9
                if abs(sol_change) > 0.005:
                    fiat = get_fiat_value("SOL", sol_change)
                    sign = "+" if sol_change > 0 else ""
                    changes_detected.append(f"<b>Native SOL:</b> {sign}{sol_change:.4f} SOL{fiat}")

            pre_tokens = meta.get('preTokenBalances', [])
            post_tokens = meta.get('postTokenBalances', [])
            
            for bal in pre_tokens:
                if bal.get('owner') == tracked:
                    amt = bal.get('uiTokenAmount', {}).get('uiAmount') or 0
                    token_balances[bal.get('mint')] = -amt
                    
            for bal in post_tokens:
                if bal.get('owner') == tracked:
                    amt = bal.get('uiTokenAmount', {}).get('uiAmount') or 0
                    mint = bal.get('mint')
                    token_balances[mint] = token_balances.get(mint, 0) + amt

            for mint, change in token_balances.items():
                if abs(change) > 0.0001:
                    sign = "+" if change > 0 else ""
                    token_name = COMMON_TOKENS.get(mint, f"Token ({mint[:4]}...{mint[-4:]})")
                    fiat = get_fiat_value(token_name, change)
                    changes_detected.append(f"<b>Token:</b> {sign}{change:,.2f} {token_name}{fiat}")

            if changes_detected:
                action_text = "\n".join(changes_detected)
                msg = (f"🟣 <b>SOL WHALE ACTIVITY</b> 🟣\n\n"
                       f"🎯 <b>Wallet:</b> <b>{wallets[tracked]}</b>\n\n"
                       f"⚡ <b>Balance Changes:</b>\n{action_text}")
                
                kb = {"inline_keyboard": [[{"text": "🔍 View on Solscan", "url": f"https://solscan.io/tx/{sig}"}]]}
                send_telegram(msg, kb)

    if len(PROCESSED_TXS) > 200: PROCESSED_TXS.pop(0)
    return "OK", 200

if __name__ == '__main__':
    app.run(port=10000)
