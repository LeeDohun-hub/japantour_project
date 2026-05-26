"""루트·정적 JS/CSS (API 경로와 분리)."""

from django.urls import path

from tour_api import views

urlpatterns = [
    path("chat/", views.serve_chat, name="chat_page"),
    path("styles.css", views.serve_styles),
    path("assets/bg-korea-theme.svg", views.serve_theme_bg),
    path("app.js", views.serve_app_js),
    path("auth.js", views.serve_auth_js),
    path("wizard.js", views.serve_wizard_js),
    path("region-areas.js", views.serve_region_areas_js),
    path("plan-map.js", views.serve_plan_map_js),
    path("link-preview.js", views.serve_link_preview_js),
    path("maps-open-url.js", views.serve_maps_open_url_js),
    path("", views.serve_home, name="home_page"),
]
