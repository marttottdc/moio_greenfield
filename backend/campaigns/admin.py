from django.contrib import admin
from campaigns.models import Campaign, Audience, CampaignDataStaging, CampaignData, AudienceMembership


class CampaignDataStagingAdmin(admin.ModelAdmin):
    list_display = ('pk', 'tenant', 'campaign_id', 'original_filename', 'created_at')


class CampaignDataAdmin(admin.ModelAdmin):
    list_display = ('pk', 'tenant', 'campaign', 'status', 'variables', 'scheduled_at', 'result', 'job')


admin.site.register(Campaign)
admin.site.register(Audience)
admin.site.register(CampaignDataStaging, CampaignDataStagingAdmin)
admin.site.register(CampaignData, CampaignDataAdmin)
admin.site.register(AudienceMembership)

