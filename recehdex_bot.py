import asyncio
from web3 import Web3
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import logging
from datetime import datetime
import os
import requests

# ================= KONFIGURASI =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"
WRIC_ADDRESS = "0xEa126036c94Ab6A384A25A70e29E2fE2D4a91e68"

RPC_URL = "https://seed-richechain.com"
DEX_URL = "https://dex.cryptoreceh.com"
PAIR_INFO_URL = "https://dex.cryptoreceh.com/info"
CREATE_TOKEN_URL = "https://app.cryptoreceh.com"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner.png"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ABI
FACTORY_ABI = [
    {"constant": True, "inputs": [], "name": "allPairsLength", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "uint256"}], "name": "allPairs", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

PAIR_ABI = [
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "_reserve0", "type": "uint112"}, {"name": "_reserve1", "type": "uint112"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

TOKEN_ABI = [
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
]

def get_token_info(token_address):
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except:
        return "Unknown", 18

def get_top_3_pairs():
    """Ambil SEMUA pair, urutkan berdasarkan total reserve (likuiditas), ambil top 3"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pair di factory: {total_pairs}")

        all_pairs = []

        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair_contract = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)

                token0 = pair_contract.functions.token0().call()
                token1 = pair_contract.functions.token1().call()
                reserves = pair_contract.functions.getReserves().call()
                reserve0_raw = reserves[0]
                reserve1_raw = reserves[1]

                # Ambil info token
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)

                # Konversi reserve ke angka normal
                reserve0 = reserve0_raw / (10 ** token0_dec)
                reserve1 = reserve1_raw / (10 ** token1_dec)

                # Hitung total likuiditas (dalam bentuk nilai, bukan USD)
                # Pakai WRIC sebagai acuan harga jika ada
                total_value = 0
                
                # Coba estimasi nilai dalam USD jika salah satu token adalah WRIC atau USDr
                if token0.lower() == WRIC_ADDRESS.lower():
                    total_value = reserve0 * 2  # asumsi 1 WRIC = 1 USD
                elif token1.lower() == WRIC_ADDRESS.lower():
                    total_value = reserve1 * 2
                else:
                    # Jika tidak ada WRIC, pakai total reserve sebagai pembanding
                    total_value = (reserve0 + reserve1)

                if total_value > 0:
                    all_pairs.append({
                        "pair_name": f"{token0_symbol}/{token1_symbol}",
                        "token0": token0_symbol,
                        "token1": token1_symbol,
                        "reserve0": reserve0,
                        "reserve1": reserve1,
                        "total_value": total_value,
                        "address": pair_address,
                        "token0_address": token0,
                        "token1_address": token1
                    })
                    logger.info(f"Pair: {token0_symbol}/{token1_symbol}, value: {total_value:.2f}")

            except Exception as e:
                logger.error(f"Error pair {i}: {e}")
                continue

        # Urutkan berdasarkan total_value (likuiditas) tertinggi
        all_pairs.sort(key=lambda x: x['total_value'], reverse=True)
        
        # Ambil top 3
        top3 = all_pairs[:3]
        logger.info(f"Top 3 pairs: {[p['pair_name'] for p in top3]}")
        
        return top3

    except Exception as e:
        logger.error(f"Error: {e}")
        return []

async def get_banner():
    try:
        response = requests.get(BANNER_URL, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

async def main():
    logger.info("RecehDEX Bot Started")
    
    if not w3.is_connected():
        logger.error("Cannot connect")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    top_pairs = get_top_3_pairs()
    
    if not top_pairs:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No pairs found")
        return
    
    # Build message
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Link trade (pake token0 dan token1)
        trade_url = f"{DEX_URL}?inputCurrency={pair['token0_address']}&outputCurrency={pair['token1_address']}"
        
        message += f"<b>{idx}. {pair['pair_name']}</b>\n"
        message += f"   💧 Reserve: <code>{pair['reserve0']:.2f} {pair['token0']} / {pair['reserve1']:.2f} {pair['token1']}</code>\n"
        message += f"   🔗 <a href='{trade_url}'>Trade Now</a>\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    
    # Tombol
    keyboard = [
        [InlineKeyboardButton("📊 RecehDEX", url=DEX_URL)],
        [InlineKeyboardButton("ℹ️ PairInfo", url=PAIR_INFO_URL)],
        [InlineKeyboardButton("✨ Create Token", url=CREATE_TOKEN_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Kirim
    banner = await get_banner()
    if banner:
        await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=banner, caption=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    logger.info("Done")

if __name__ == "__main__":
    asyncio.run(main())
