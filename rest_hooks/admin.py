from django.contrib import admin
from django.conf import settings
from django import forms
from rest_hooks.models import Hook


HOOK_EVENTS = getattr(settings, 'HOOK_EVENTS', None)
if HOOK_EVENTS is None:
    raise Exception("You need to define settings.HOOK_EVENTS!")


class HookForm(forms.ModelForm):
    """
    Model form to handle registered events, asuring
    only events declared on HOOK_EVENTS settings
    can be registered.
    """
    ADMIN_EVENTS = [(x, x) for x in HOOK_EVENTS.keys()]

    class Meta:
        model = Hook
        fields = ['user', 'target', 'event']

    def __init__(self, *args, **kwargs):
        super(HookForm, self).__init__(*args, **kwargs)
        self.fields['event'] = forms.ChoiceField(choices=self.ADMIN_EVENTS)


class HookAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Hook._meta.fields]
    raw_id_fields = ['user', ]
    form = HookForm

admin.site.register(Hook, HookAdmin)
