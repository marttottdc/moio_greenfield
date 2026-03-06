from portal.webhooks.registry import webhook_handler


@webhook_handler()
def campaign_receiver(payload, headers, content_type, cfg):
    pass
