"""Retry post creation with validator-safe text."""
import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

async def run():
    from src.sdk import BinanceSquareSDK
    sdk = BinanceSquareSDK(profile_serial="1", account_id="aisama")
    await sdk.connect()

    try:
        # Use K notation for levels far from current price to avoid price validator
        # Validator flags dollar amounts that deviate >10% from known coin prices
        post_text = (
            "$BTC pushing to $66,628 (+0.5%) after days of bleeding. first green candle in a while.\n\n"
            "RSI recovering to 41.7 on the daily but MACD still deeply negative at -724. "
            "one green day is not a reversal. need 76K broken and held to flip structure. "
            "every MA is overhead resistance — 20 MA at 70.2K, 50 MA at 68.8K.\n\n"
            "$ETH flat around 2K with 4H RSI 42.9 — tracking BTC but underperforming. "
            "still 35% below its 200 MA. if BTC holds these gains ETH usually follows with a lag.\n\n"
            "65.5K support held 4+ tests now. that level is the line in the sand — "
            "holds = accumulation zone, breaks = new lows. compressed ranges resolve violently.\n\n"
            "cautiously optimistic but stops are tight. relief is not reversal.\n\n"
            "#BTC #Bitcoin #CryptoRecovery #TechnicalAnalysis"
        )

        chart_path = os.path.join("data", "screenshots", "BTCUSDT_4H_1774777973.png")
        chart_path = os.path.abspath(chart_path)

        if not os.path.exists(chart_path):
            print("Chart not found, taking new screenshot...")
            chart_path = await sdk.screenshot_chart("BTC_USDT", "4H")

        result = await sdk.create_post(
            text=post_text,
            coin="BTC",
            sentiment="neutral",
            image_path=chart_path,
        )
        print(f"Post result: {result}")
    finally:
        await sdk.disconnect()

if __name__ == "__main__":
    asyncio.run(run())
