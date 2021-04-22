from django.contrib import admin

from .forms import ProfileForm
from .models import Profile
from .models import Post


# Register your models here.

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'external_id', 'username', 'is_admin')
    form = ProfileForm


@admin.register(Post)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'profile', 'external_id', 'price', 'text', 'created_at', 'reviewed_at', 'status', 'type_p',
        'image_file_id')
