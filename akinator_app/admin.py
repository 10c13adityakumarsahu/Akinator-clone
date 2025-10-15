from django.contrib import admin
from .models import Character, Question, GameSession

admin.site.register(Character)
admin.site.register(Question)
admin.site.register(GameSession)
