from discord_webhook import DiscordWebhook
from valuation.config import settings

def test():
    webhook_url = settings.discord_webhook_url
    if not webhook_url:
        print("Webhook URL not found in config")
        return
        
    webhook = DiscordWebhook(url=webhook_url, content="Hệ thống định giá tự động đã kết nối thành công với Discord! 🚀 [Test Message Phase 5]")
    response = webhook.execute()
    print("Response status code:", response.status_code)

if __name__ == "__main__":
    test()
