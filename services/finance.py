import httpx


def format_price(value):
    """Format numeric prices without crashing when an API omits a value."""
    return f"{value:,}" if isinstance(value, (int, float)) else "--"


async def get_market_rates() -> str:
    """Tamamen ücretsiz halka açık API'lerden döviz ve kripto kurlarını çeker."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Döviz kurları (Frankfurter - Avrupa Merkez Bankası verisi, ücretsiz ve anahtarsız)
            currency_url = "https://api.frankfurter.dev/v1/latest?base=TRY&symbols=USD,EUR,GBP"
            c_res = await client.get(currency_url)
            c_res.raise_for_status()
            c_data = c_res.json()
            rates = c_data.get("rates", {})

            # Frankfurter base=TRY verince 1 TL = X döviz verir, biz 1 Döviz = X TL istiyoruz (1 / rate)
            usd_try = round(1 / rates.get("USD", 1), 2) if rates.get("USD") else "--"
            eur_try = round(1 / rates.get("EUR", 1), 2) if rates.get("EUR") else "--"
            gbp_try = round(1 / rates.get("GBP", 1), 2) if rates.get("GBP") else "--"

            # 2. Kripto kurları (CoinGecko public API)
            crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd,try"
            crypto_res = await client.get(crypto_url)
            crypto_res.raise_for_status()
            crypto_data = crypto_res.json()

            btc_usd = crypto_data.get("bitcoin", {}).get("usd", "--")
            eth_usd = crypto_data.get("ethereum", {}).get("usd", "--")
            sol_usd = crypto_data.get("solana", {}).get("usd", "--")

            return (
                f"💹 *Piyasa & Finans Özeti*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 *Dolar (USD):* `{usd_try} ₺`\n"
                f"💶 *Euro (EUR):* `{eur_try} ₺`\n"
                f"💷 *Sterlin (GBP):* `{gbp_try} ₺`\n\n"
                f"🪙 *Kripto Piyasası*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🟠 *Bitcoin (BTC):* `${format_price(btc_usd)}`\n"
                f"🔷 *Ethereum (ETH):* `${format_price(eth_usd)}`\n"
                f"🟣 *Solana (SOL):* `${format_price(sol_usd)}`\n"
            )
    except Exception as e:
        return f"⚠️ Finans verileri alınırken bir hata oluştu: {str(e)}"
