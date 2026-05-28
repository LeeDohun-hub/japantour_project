from django.urls import path

from tour_api import views

urlpatterns = [
    path("health/", views.api_health, name="api_health"),
    path("flights/", views.api_flights, name="api_flights"),
    path("places/search/", views.api_places_search, name="api_places_search"),
    path("address/juso/", views.api_juso_search, name="api_juso_search"),
    path("places/enrich/", views.api_places_enrich, name="api_places_enrich"),
    path("link-preview/", views.api_link_preview, name="api_link_preview"),
    path("maps/config/", views.api_maps_config, name="api_maps_config"),
    path("photo/", views.api_photo, name="api_photo"),
    path("places-debug/", views.api_places_debug, name="api_places_debug"),
    path("plan-snapshot/", views.api_plan_snapshot, name="api_plan_snapshot"),
    path("chat/", views.api_chat, name="api_chat"),
    path("chat/stream/", views.api_chat_stream, name="api_chat_stream"),
    path("auth/register/", views.api_register, name="api_register"),
    path("auth/login/", views.api_login, name="api_login"),
    path("auth/logout/", views.api_logout, name="api_logout"),
    path("auth/me/", views.api_me, name="api_me"),
    path("auth/oauth/google/", views.oauth_google_start, name="oauth_google_start"),
    path("auth/oauth/google/callback/", views.oauth_google_callback, name="oauth_google_callback"),
    path("auth/oauth/line/", views.oauth_line_start, name="oauth_line_start"),
    path("auth/oauth/line/callback/", views.oauth_line_callback, name="oauth_line_callback"),
]
