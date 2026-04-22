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

# ================= ADDRESS =================
FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"

RPC_URL = "https://seed-richechain.com"
DEX_URL = "https://dex.cryptoreceh.com"
PAIR_INFO_URL = "https://dex.cryptoreceh.com/info"
CREATE_TOKEN_URL = "https://app.cryptoreceh.com"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner.png"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= ABI =================
FACTORY_ABI = [
    {"inputs": [], "name": "allPairsLength", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "uint256"}], "name": "allPairs", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"}
]

PAIR_ABI = [
    {"inputs": [], "name": "getReserves", "outputs": [{"type": "uint112"}, {"type": "uint112"}, {"type": "uint32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token0", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"}
]

TOKEN_ABI = [
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"}
]

def get_token_info(token_address):
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except:
        return "Unknown", 18

def get_top_3_pairs():
    """Ambil semua pair, urutkan berdasarkan total reserve (likuiditas tertinggi)"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pairs: {total_pairs}")
        
        pairs_data = []
        
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair.functions.token0().call()
                token1 = pair.functions.token1().call()
                reserves = pair.functions.getReserves().call()
                
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                reserve0 = reserves[0] / (10 ** token0_dec)
                reserve1 = reserves[1] / (10 ** token1_dec)
                
                # Hitung total nilai likuiditas (pakai USD sebagai acuan jika ada)
                total_value = 0
                price_in_usd = 0
                
                # Jika pair dengan USD, hitung harga dalam USD
                if token0.lower() == USD_ADDRESS.lower():
                    price_in_usd = reserve1 / reserve0 if reserve0 > 0 else 0
                    total_value = reserve0 * 2
                elif token1.lower() == USD_ADDRESS.lower():
                    price_in_usd = reserve0 / reserve1 if reserve1 > 0 else 0
                    total_value = reserve1 * 2
                else:
                    # Pair tanpa USD, pakai total reserve sebagai pembanding
                    total_value = reserve0 + reserve1
                
                if total_value > 0:
                    pairs_data.append({
                        "pair_name": f"{token0_symbol}/{token1_symbol}",
                        "token0": token0_symbol,
                        "token1": token1_symbol,
                        "reserve0": reserve0,
                        "reserve1": reserve1,
                        "total_value": total_value,
                        "price_in_usd": price_in_usd,
                        "pair_address": pair_address,
                        "token0_address": token0,
                        "token1_address": token1
                    })
                    logger.info(f"Pair: {token0_symbol}/{token1_symbol}, value: {total_value:.2f}")
                    
            except Exception as e:
                logger.error(f"Error pair {i}: {e}")
                continue
        
        # Urutkan berdasarkan total_value (likuiditas) tertinggi
        pairs_data.sort(key=lambda x: x['total_value'], reverse=True)
        
        # Ambil top 3
        top3 = pairs_data[:3]
        for p in top3:
            logger.info(f"Top: {p['pair_name']} - value: {p['total_value']:.2f}")
        
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
    logger.info("=" * 50)
    logger.info("RecehDEX Bot - Top 3 Pairs (Data Real dari Factory)")
    logger.info("=" * 50)
    
    if not w3.is_connected():
        logger.error("Cannot connect to Riche Chain")
        return
    
    logger.info(f"Connected - Block: {w3.eth.block_number}")
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    top_pairs = get_top_3_pairs()
    
    if not top_pairs:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No pairs found")
        return
    
    # Build message
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Tampilkan reserve
        message += f"<b>{idx}. {pair['pair_name']}</b>\n"
        message += f"   💧 Reserve: <code>{pair['reserve0']:,.2f} {pair['token0']} / {pair['reserve1']:,.2f} {pair['token1']}</code>\n"
        
        # Tampilkan harga dalam USD jika ada
        if pair['price_in_usd'] > 0:
            price = pair['price_in_usd']
            if price < 0.0001:
                price_str = f"${price:.10f}"
            elif price < 0.01:
                price_str = f"${price:.6f}"
            elif price < 1:
                price_str = f"${price:.5f}"
            else:
                price_str = f"${price:.4f}"
            message += f"   💰 Harga: <code>{price_str}</code>\n"
        
        # Link trade (pake token0 dan token1 asli)
        trade_url = f"{DEX_URL}?inputCurrency={pair['token0_address']}&outputCurrency={pair['token1_address']}"
        message += f"   🔗 <a href='{trade_url}'>Trade Now</a>\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
    message += "📊 Data real dari Factory RecehDEX"
    
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
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=banner,
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    logger.info("Done")

if __name__ == "__main__":
    asyncio.run(main())
