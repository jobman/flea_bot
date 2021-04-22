from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = (
            'external_id',
            'username',
            'is_admin',
        )
        widgets = {
            'username' : forms.TextInput,
        }
