from django.urls import path
from . import views

urlpatterns = [
    path('start_game/', views.start_game),
    path('answer/', views.answer_question),
    path('get_result/', views.get_result),
    path("add_character/", views.add_character),
    path('get-character-info/', views.get_character_info_api, name='get_character_info'),
]
