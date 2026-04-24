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
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"  # USDr
WRIC_ADDRESS = "0xEa126036c94Ab6A384A25A70e29E2fE2D4a91e68"  # WRIC

RPC_URL = "https://seed-richechain.com"
DEX_URL = "https://dex.cryptoreceh.com/riche"
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

STABLE_ADDRESSES = [USD_ADDRESS.lower(), WRIC_ADDRESS.lower()]

def get_token_info(token_address):
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except:
        return "Unknown", 18

def is_stable(token_address):
    return token_address.lower() in STABLE_ADDRESSES

def get_stable_type(stable_address):
    """Return 'USD' for USDr, 'WRIC' for WRIC"""
    if stable_address.lower() == USD_ADDRESS.lower():
        return "USD"
    elif stable_address.lower() == WRIC_ADDRESS.lower():
        return "WRIC"
    return "Unknown"

def get_top_3_pairs_with_stable():
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pairs: {total_pairs}")
        
        valid_pairs = []
        
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair.functions.token0().call().lower()
                token1 = pair.functions.token1().call().lower()
                reserves = pair.functions.getReserves().call()
                reserve0_raw = reserves[0]
                reserve1_raw = reserves[1]
                
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                if not (is_stable(token0) or is_stable(token1)):
                    continue
                
                # Tentukan mana stable dan mana token
                if is_stable(token0):
                    stable_address = token0
                    stable_symbol = token0_symbol
                    stable_reserve = reserve0_raw / (10 ** token0_dec)
                    token_address = token1
                    token_symbol = token1_symbol
                    token_reserve = reserve1_raw / (10 ** token1_dec)
                else:
                    stable_address = token1
                    stable_symbol = token1_symbol
                    stable_reserve = reserve1_raw / (10 ** token1_dec)
                    token_address = token0
                    token_symbol = token0_symbol
                    token_reserve = reserve0_raw / (10 ** token0_dec)
                
                # Hitung harga (dalam stable coin)
                if token_reserve > 0:
                    price_in_stable = stable_reserve / token_reserve
                else:
                    price_in_stable = 0
                
                liquidity_usd = stable_reserve * 2
                
                if liquidity_usd > 0.01 and price_in_stable > 0:
                    stable_type = get_stable_type(stable_address)
                    
                    valid_pairs.append({
                        "pair_name": f"{token_symbol}/{stable_symbol}",
                        "token_symbol": token_symbol,
                        "token_address": token_address,
                        "stable_symbol": stable_symbol,
                        "stable_address": stable_address,
                        "stable_type": stable_type,  # "USD" or "WRIC"
                        "price": price_in_stable,   # Harga dalam stable coin (USD atau WRIC)
                        "liquidity": liquidity_usd,
                        "token_reserve": token_reserve,
                        "stable_reserve": stable_reserve,
                    })
                    logger.info(f"{token_symbol}/{stable_symbol}: price={price_in_stable:.8f} {stable_type}, liq=${liquidity_usd:.2f}")
                    
            except Exception as e:
                logger.error(f"Error pair {i}: {e}")
                continue
        
        valid_pairs.sort(key=lambda x: x['liquidity'], reverse=True)
        return valid_pairs[:3]
        
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
    logger.info("RecehDEX Bot - Top 3 Pairs")
    logger.info("=" * 50)
    
    if not w3.is_connected():
        logger.error("Cannot connect to Riche Chain")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    top_pairs = get_top_3_pairs_with_stable()
    
    if not top_pairs:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No pairs found")
        return
    
    # Build message
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Format price dengan unit yang benar
        price = pair['price']
        stable_type = pair['stable_type']
        
        # Display price dengan unit yang sesuai
        if stable_type == "USD":
            price_unit = "$"
        else:  # WRIC
            price_unit = ""
        
        if price < 0.000001:
            price_str = f"{price_unit}{price:.12f}"
        elif price < 0.0001:
            price_str = f"{price_unit}{price:.10f}"
        elif price < 0.01:
            price_str = f"{price_unit}{price:.8f}"
        elif price < 1:
            price_str = f"{price_unit}{price:.6f}"
        else:
            price_str = f"{price_unit}{price:.4f}"
        
        # Tambahkan satuan untuk WRIC
        if stable_type == "WRIC":
            price_str = f"{price_str} WRIC"
        
        # Format liquidity
        liq = pair['liquidity']
        liq_str = f"${liq:,.2f}" if liq >= 1 else f"${liq:.2f}"
        
        trade_url = f"{DEX_URL}?inputCurrency={pair['token_address']}&outputCurrency={pair['stable_address']}"
        
        message += f"<b>{idx}. {pair['pair_name']}</b>\n"
        message += f"   💰 Price: <code>{price_str}</code>\n"
        message += f"   💧 Liquidity: <code>{liq_str}</code>\n"
        message += f"   🔗 <a href='{trade_url}'>Trade Now</a>\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
    message += "💰 Data RecehDEX jaringan RicheChain"
    
    # Tombol
    keyboard = [
        [InlineKeyboardButton("📊 RecehDEX", url=DEX_URL)],
        [InlineKeyboardButton("ℹ️ PairInfo", url=PAIR_INFO_URL)],
        [InlineKeyboardButton("✨ CreateToken", url=CREATE_TOKEN_URL)]
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
