from django.urls import path
from . import views

urlpatterns = [
    path('start_game/', views.start_game),
    path('answer_question/', views.answer_question),
    path('get_result/', views.get_result),
]
