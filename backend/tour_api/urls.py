from django.urls import path

from tour_api import views

urlpatterns = [
    path("health/", views.api_health, name="api_health"),
    path("chat/", views.api_chat, name="api_chat"),
]
