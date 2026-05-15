from django.urls import path

from tour_api import views

urlpatterns = [
    path("health/", views.api_health, name="api_health"),
    path("chat/", views.api_chat, name="api_chat"),
    path("auth/register/", views.api_register, name="api_register"),
    path("auth/login/", views.api_login, name="api_login"),
    path("auth/logout/", views.api_logout, name="api_logout"),
    path("auth/me/", views.api_me, name="api_me"),
    path("auth/oauth/google/", views.oauth_google_start, name="oauth_google_start"),
    path("auth/oauth/google/callback/", views.oauth_google_callback, name="oauth_google_callback"),
    path("auth/oauth/line/", views.oauth_line_start, name="oauth_line_start"),
    path("auth/oauth/line/callback/", views.oauth_line_callback, name="oauth_line_callback"),
]
