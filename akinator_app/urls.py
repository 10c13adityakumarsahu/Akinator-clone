from django.urls import path
from . import views

urlpatterns = [
    path('start_game/', views.start_game),
    path('answer/', views.answer_question),
    path('get_result/', views.get_result),
    path("add_character/", views.add_character),
    path("learn/", views.learn_from_feedback),
]
