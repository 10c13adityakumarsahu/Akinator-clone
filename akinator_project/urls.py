"""
URL configuration for akinator_project project.
"""
from django.contrib import admin
from django.urls import path, include
from akinator_app import views as akinator_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('akinator_app.urls')),
    path('', akinator_views.index_view, name='index'),
]

