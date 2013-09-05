from django.contrib import admin

from rest_hooks.models import Hook


class HookAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Hook._meta.fields]
    raw_id_fields = ['user',]
admin.site.register(Hook, HookAdmin)
